import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { Table } from "./table";

interface Row {
  id: string;
  name: string;
  status: string;
}

const columns = [
  { key: "name", header: "Name" },
  { key: "status", header: "Status" },
];

const data: Row[] = [
  { id: "1", name: "Agent A", status: "running" },
  { id: "2", name: "Agent B", status: "completed" },
];

describe("Table", () => {
  it("renders headers", () => {
    render(<Table columns={columns} data={data} rowKey={(r) => r.id} />);
    expect(screen.getByText("Name")).toBeInTheDocument();
    expect(screen.getByText("Status")).toBeInTheDocument();
  });

  it("renders rows", () => {
    render(<Table columns={columns} data={data} rowKey={(r) => r.id} />);
    expect(screen.getByText("Agent A")).toBeInTheDocument();
    expect(screen.getByText("Agent B")).toBeInTheDocument();
  });

  it("shows empty message when no data", () => {
    render(
      <Table<Row> columns={columns} data={[]} rowKey={(r) => r.id} emptyMessage="Nada aqui" />
    );
    expect(screen.getByText("Nada aqui")).toBeInTheDocument();
  });

  it("uses custom render function", () => {
    const customColumns: { key: string; header: string; render?: (row: Row) => React.ReactNode }[] = [
      {
        key: "name",
        header: "Name",
        render: (row: Row) => <strong>{row.name}</strong>,
      },
    ];
    render(<Table columns={customColumns} data={data} rowKey={(r) => r.id} />);
    expect(screen.getByText("Agent A").tagName).toBe("STRONG");
  });
});
