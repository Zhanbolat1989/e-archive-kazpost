// Компактный набор штриховых SVG-иконок (24px grid, stroke 2) для навигации.
const PATHS = {
  dashboard: <><rect x="3" y="3" width="7" height="9" rx="1.5" /><rect x="14" y="3" width="7" height="5" rx="1.5" /><rect x="14" y="12" width="7" height="9" rx="1.5" /><rect x="3" y="16" width="7" height="5" rx="1.5" /></>,
  document: <><path d="M6 2h8l5 5v13a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2z" /><path d="M14 2v5h5" /><path d="M8 13h8M8 17h5" /></>,
  folder: <path d="M3 7a2 2 0 0 1 2-2h4l2 3h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7z" />,
  list: <><path d="M8 6h13M8 12h13M8 18h13" /><circle cx="4" cy="6" r="1.3" fill="currentColor" stroke="none" /><circle cx="4" cy="12" r="1.3" fill="currentColor" stroke="none" /><circle cx="4" cy="18" r="1.3" fill="currentColor" stroke="none" /></>,
  issue: <><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" /><path d="M14 16l5-4-5-4" /><path d="M19 12H8" /></>,
  trash: <><path d="M4 7h16" /><path d="M9 7V4h6v3" /><path d="M6 7l1 13h10l1-13" /><path d="M10 11v6M14 11v6" /></>,
  bot: <><rect x="4" y="8" width="16" height="11" rx="2.5" /><path d="M12 8V4M8 4h8" /><circle cx="9" cy="13" r="1.2" fill="currentColor" stroke="none" /><circle cx="15" cy="13" r="1.2" fill="currentColor" stroke="none" /><path d="M9.5 16.5h5" /></>,
  upload: <><path d="M12 16V4" /><path d="M7 9l5-5 5 5" /><path d="M4 20h16" /></>,
};

export default function Icon({ name, size = 18 }) {
  return (
    <svg
      width={size} height={size} viewBox="0 0 24 24"
      fill="none" stroke="currentColor" strokeWidth="2"
      strokeLinecap="round" strokeLinejoin="round"
      aria-hidden="true" style={{ flexShrink: 0 }}
    >
      {PATHS[name]}
    </svg>
  );
}
