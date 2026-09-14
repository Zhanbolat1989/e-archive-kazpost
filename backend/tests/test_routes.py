# -*- coding: utf-8 -*-
"""Подстановка согласующих по оргструктуре (ТС-176 п. 4.10)."""
import pytest

from app.services import routes

UNITS = {
    "root": routes.Unit("Центральный аппарат", None, "ceo@kazpost.kz"),
    "fin": routes.Unit("Департамент финансов", "root", "fin.head@kazpost.kz"),
    "acc": routes.Unit("Бухгалтерия", "fin", "acc.head@kazpost.kz"),
    "arch": routes.Unit("Архив", "root", ""),
}
USERS = {
    "ceo@kazpost.kz": "Председатель правления",
    "fin.head@kazpost.kz": "Директор департамента",
    "acc.head@kazpost.kz": "Главный бухгалтер",
    "lawyer@kazpost.kz": "Юрист",
    "clerk@kazpost.kz": "Архивариус",
}
HEAD = {"kind": "head"}
PARENT = {"kind": "parent_head"}


def _emails(plan):
    return [s.approver_email for s in plan]


def test_heads_follow_department_tree():
    plan = routes.resolve([HEAD, PARENT, {"kind": "user", "value": "lawyer@kazpost.kz"}],
                          "acc", UNITS, USERS, "clerk@kazpost.kz")
    assert _emails(plan) == ["acc.head@kazpost.kz", "fin.head@kazpost.kz", "lawyer@kazpost.kz"]
    assert plan[0].basis == "Руководитель: Бухгалтерия"
    assert plan[1].approver_name == "Директор департамента"


def test_head_of_selected_department_needs_no_object_department():
    plan = routes.resolve([{"kind": "department_head", "value": "root"}],
                          None, UNITS, USERS, "clerk@kazpost.kz")
    assert _emails(plan) == ["ceo@kazpost.kz"]


def test_initiator_and_repeats_are_skipped():
    plan = routes.resolve([HEAD, {"kind": "department_head", "value": "acc"}, PARENT],
                          "acc", UNITS, USERS, "acc.head@kazpost.kz")
    assert _emails(plan) == ["fin.head@kazpost.kz"]


def test_route_of_only_initiator_is_rejected():
    with pytest.raises(ValueError, match="совпадают с инициатором"):
        routes.resolve([HEAD], "acc", UNITS, USERS, "acc.head@kazpost.kz")


@pytest.mark.parametrize("steps, department, message", [
    ([HEAD], None, "не определено подразделение"),
    ([HEAD], "arch", "нет действующего руководителя"),
    ([PARENT], "root", "нет вышестоящего"),
    ([{"kind": "user", "value": "gone@kazpost.kz"}], "acc", "не найден или отключён"),
    ([{"kind": "department_head", "value": "nope"}], None, "не найдено в оргструктуре"),
])
def test_unresolvable_step_blocks_the_route(steps, department, message):
    with pytest.raises(ValueError, match=message):
        routes.resolve(steps, department, UNITS, USERS, "clerk@kazpost.kz")


def test_disabled_head_is_not_an_approver():
    users = {k: v for k, v in USERS.items() if k != "fin.head@kazpost.kz"}
    with pytest.raises(ValueError, match="Департамент финансов"):
        routes.resolve([PARENT], "acc", UNITS, users, "clerk@kazpost.kz")


def test_template_steps_are_validated():
    assert routes.normalize_steps([{"kind": "head", "value": "x"}]) == [{"kind": "head", "value": ""}]
    with pytest.raises(ValueError, match="хотя бы один шаг"):
        routes.normalize_steps([])
    with pytest.raises(ValueError, match="Шаг 1"):
        routes.normalize_steps([{"kind": "boss"}])
    with pytest.raises(ValueError, match="выберите подразделение"):
        routes.normalize_steps([{"kind": "department_head"}])


def test_department_tree_cycles():
    parents = {"root": None, "fin": "root", "acc": "fin"}
    assert routes.creates_cycle("fin", "acc", parents) is True
    assert routes.creates_cycle("fin", "fin", parents) is True
    assert routes.creates_cycle("acc", "root", parents) is False
    assert routes.creates_cycle("fin", None, parents) is False
