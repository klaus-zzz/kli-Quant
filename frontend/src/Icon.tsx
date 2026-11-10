// 图标沿用已确认的细线样式，装饰图形不重复读屏按钮名称。
const paths = {
  brand: "M5 3v18M19 3 8 12l11 9M8 12h12",
  plus: "M12 5v14M5 12h14",
  search: "M16 16l5 5M17 10a7 7 0 1 1-14 0 7 7 0 0 1 14 0",
  layers: "m3 7 9-4 9 4-9 4-9-4Zm0 5 9 4 9-4M3 17l9 4 9-4",
  panelLeft: "M4 4h16v16H4ZM9 4v16",
  panelRight: "M4 4h16v16H4ZM15 4v16",
  arrowUpRight: "M6 18 18 6M7 6h11v11",
  arrowUp: "M12 19V5m-6 6 6-6 6 6",
  chevronDown: "m6 9 6 6 6-6",
  close: "m6 6 12 12M6 18 18 6",
  file: "M14 3H5v18h14V8l-5-5Zm0 0v5h5M8 12h8m-8 4h6",
  globe:
    "M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0ZM3 12h18M12 3c-5 5-5 13 0 18 5-5 5-13 0-18",
  code: "m8 6-6 6 6 6m8-12 6 6-6 6m-3-14-2 16",
  sliders:
    "M4 7h9m4 0h3M4 17h3m4 0h9M17 7a2 2 0 1 1-4 0 2 2 0 0 1 4 0M11 17a2 2 0 1 1-4 0 2 2 0 0 1 4 0",
  logout: "M9 4H4v16h5M10 12h11m-5-5 5 5-5 5",
};
export default function Icon({ name }: { name: keyof typeof paths }) {
  return (
    <span data-icon={name}>
      <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <path d={paths[name]} />
      </svg>
    </span>
  );
}
