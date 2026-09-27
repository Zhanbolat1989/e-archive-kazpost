"""Приём пакетов оцифровки и восстановление архива.

Модуль импорта — мост между услугой оцифровки и системой: АРМ сканирования
отдаёт ZIP с файлами и manifest.xml, система создаёт по нему дела, карточки
документов и запускает распознавание. Тот же механизм принимает собственную
резервную копию архива — восстановление это импорт выгруженного пакета.
"""
import json
import threading

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import ImportJob, Role, User
from ..schemas import ImportJobOut
from ..security import require_roles
from ..services import audit, importer

router = APIRouter(prefix="/api/imports", tags=["imports"])

MAX_PACKAGE = 2 * 1024 * 1024 * 1024      # 2 ГБ — партия оцифровки целиком


def _out(job: ImportJob) -> ImportJobOut:
    # Ошибки загрузки хранятся строкой JSON — разбираем их до проверки схемой,
    # иначе она отвергает запись целиком.
    try:
        errors = json.loads(job.errors or "[]")
    except ValueError:
        errors = []
    return ImportJobOut(
        id=job.id, filename=job.filename, status=job.status, total=job.total,
        created_documents=job.created_documents, created_cases=job.created_cases,
        skipped_duplicates=job.skipped_duplicates, errors=errors,
        created_by=job.created_by, created_at=job.created_at,
        finished_at=job.finished_at,
    )


@router.get("", response_model=list[ImportJobOut])
def list_jobs(db: Session = Depends(get_db),
              _: User = Depends(require_roles(Role.admin, Role.archivist))):
    rows = (db.query(ImportJob)
            .order_by(ImportJob.created_at.desc()).limit(100).all())
    return [_out(j) for j in rows]


@router.get("/{job_id}", response_model=ImportJobOut)
def get_job(job_id: str, db: Session = Depends(get_db),
            _: User = Depends(require_roles(Role.admin, Role.archivist))):
    job = db.get(ImportJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Задание импорта не найдено")
    return _out(job)


@router.post("", response_model=ImportJobOut, status_code=202)
def upload_package(request: Request, file: UploadFile = File(...),
                   db: Session = Depends(get_db),
                   user: User = Depends(require_roles(Role.admin, Role.archivist))):
    """Принимает ZIP-пакет и запускает разбор в фоне.

    Отвечаем сразу: партия может содержать тысячи документов, каждый из которых
    ещё и распознаётся. Ход загрузки виден в карточке задания.
    """
    data = file.file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Пустой файл")
    if len(data) > MAX_PACKAGE:
        raise HTTPException(status_code=413, detail="Пакет больше 2 ГБ")
    # Проверяем манифест синхронно: непригодный пакет должен отклоняться сразу,
    # а не «приниматься» и падать где-то в фоне.
    try:
        _, root = importer.read_manifest(data)
        total = importer.count_documents(root)
    except importer.ImportError_ as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not total:
        raise HTTPException(status_code=400,
                            detail="В манифесте пакета нет ни одного документа")

    job = ImportJob(filename=file.filename, total=total, created_by=user.email)
    db.add(job)
    db.commit()
    db.refresh(job)
    audit.record(db, user, "import.start", "import", job.id,
                 f"{file.filename}: документов в пакете {total}", request=request)
    # Отдельный поток, а не BackgroundTasks: задание живёт минутами и часами,
    # и оно не должно удерживать обработчик запроса.
    threading.Thread(target=importer.run_job,
                     args=(job.id, data, user.email), daemon=True).start()
    return _out(job)
