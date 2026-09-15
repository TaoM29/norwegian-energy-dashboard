function save(filename: string, content: string, type: string) {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function downloadJson(filename: string, data: unknown) {
  save(filename, JSON.stringify(data, null, 2), "application/json");
}

export function downloadCsv(filename: string, rows: Record<string, unknown>[]) {
  const columns = [...new Set(rows.flatMap((row) => Object.keys(row)))];
  const escape = (value: unknown) => {
    const text =
      value == null
        ? ""
        : typeof value === "object"
          ? JSON.stringify(value)
          : String(value);
    return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
  };
  save(
    filename,
    [
      columns.map(escape).join(","),
      ...rows.map((row) => columns.map((key) => escape(row[key])).join(",")),
    ].join("\n"),
    "text/csv;charset=utf-8",
  );
}
