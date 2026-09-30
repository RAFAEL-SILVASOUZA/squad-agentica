import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { DataTable } from "./data-table";

interface TestRow {
  id: string;
  name: string;
  category: string;
  usageCount: number;
}

const ROWS: TestRow[] = [
  { id: "1", name: "Revisar código", category: "code", usageCount: 2 },
  { id: "2", name: "Gerar docs", category: "docs", usageCount: 0 },
  { id: "3", name: "Revisar infra", category: "infra", usageCount: 1 },
];

const COLUMNS: import("./data-table").DataTableColumn<TestRow>[] = [
  { key: "name", header: "Nome", sortable: true },
  { key: "category", header: "Categoria", sortable: true },
  { key: "usageCount", header: "Usos", render: (row) => `${row.usageCount} agentes` },
];

const FILTERS: import("./data-table").DataTableFilter[] = [
  {
    key: "category",
    label: "Categoria",
    options: [
      { value: "code", label: "Código" },
      { value: "docs", label: "Documentação" },
      { value: "infra", label: "Infraestrutura" },
    ],
  },
];

const MENU_ITEMS = [
  { label: "Editar", action: "edit" },
  { label: "Duplicar", action: "duplicate" },
  { label: "Excluir", action: "delete", danger: true },
];

beforeEach(() => {
  vi.restoreAllMocks();
  // jsdom não implementa matchMedia.
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: vi.fn().mockImplementation((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })),
  });
});

describe("DataTable", () => {
  it("renders all rows", () => {
    render(<DataTable columns={COLUMNS} rows={ROWS} rowKey={(r) => r.id} />);
    expect(screen.getByText("Revisar código")).toBeInTheDocument();
    expect(screen.getByText("Gerar docs")).toBeInTheDocument();
    expect(screen.getByText("Revisar infra")).toBeInTheDocument();
  });

  it("filters rows by search (accent-insensitive, case-insensitive)", () => {
    render(
      <DataTable
        columns={COLUMNS}
        rows={ROWS}
        rowKey={(r) => r.id}
        searchPlaceholder="Buscar…"
      />
    );
    const search = screen.getByPlaceholderText("Buscar…");
    fireEvent.change(search, { target: { value: "revis" } });
    expect(screen.getByText("Revisar código")).toBeInTheDocument();
    expect(screen.getByText("Revisar infra")).toBeInTheDocument();
    expect(screen.queryByText("Gerar docs")).not.toBeInTheDocument();
  });

  it("filters rows by category select", () => {
    render(
      <DataTable
        columns={COLUMNS}
        rows={ROWS}
        rowKey={(r) => r.id}
        filters={FILTERS}
      />
    );
    const select = screen.getByLabelText("Categoria");
    fireEvent.change(select, { target: { value: "docs" } });
    expect(screen.getByText("Gerar docs")).toBeInTheDocument();
    expect(screen.queryByText("Revisar código")).not.toBeInTheDocument();
  });

  it("shows usage count via render function", () => {
    render(<DataTable columns={COLUMNS} rows={ROWS} rowKey={(r) => r.id} />);
    expect(screen.getByText("2 agentes")).toBeInTheDocument();
    expect(screen.getByText("0 agentes")).toBeInTheDocument();
    expect(screen.getByText("1 agentes")).toBeInTheDocument();
  });

  it("sorts by column when clicking header", () => {
    render(<DataTable columns={COLUMNS} rows={ROWS} rowKey={(r) => r.id} />);
    const nameHeader = screen.getByRole("button", { name: /Nome/ });
    fireEvent.click(nameHeader);
    // After sorting by name ascending: "Gerar docs" should come first
    const rows = screen.getAllByRole("row");
    // First data row (index 1, after header)
    expect(rows[1]).toHaveTextContent("Gerar docs");
  });

  it("shows row menu with actions", () => {
    const onRowMenu = vi.fn();
    render(
      <DataTable
        columns={COLUMNS}
        rows={ROWS}
        rowKey={(r) => r.id}
        onRowMenu={onRowMenu}
        rowMenuItems={MENU_ITEMS}
      />
    );
    // Click the menu button for the first row
    const menuBtn = screen.getAllByRole("button", { name: /Ações/ })[0];
    fireEvent.click(menuBtn);
    expect(screen.getByRole("menu")).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Editar" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Duplicar" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Excluir" })).toBeInTheDocument();
  });

  it("calls onRowMenu with row and action", () => {
    const onRowMenu = vi.fn();
    render(
      <DataTable
        columns={COLUMNS}
        rows={ROWS}
        rowKey={(r) => r.id}
        onRowMenu={onRowMenu}
        rowMenuItems={MENU_ITEMS}
      />
    );
    const menuBtn = screen.getAllByRole("button", { name: /Ações/ })[0];
    fireEvent.click(menuBtn);
    fireEvent.click(screen.getByRole("menuitem", { name: "Editar" }));
    expect(onRowMenu).toHaveBeenCalledWith(ROWS[0], "edit");
  });

  it("shows empty message when no rows", () => {
    render(
      <DataTable
        columns={COLUMNS}
        rows={[]}
        rowKey={(r) => r.id}
        emptyMessage="Nenhum item encontrado"
      />
    );
    expect(screen.getByText("Nenhum item encontrado")).toBeInTheDocument();
  });

  it("shows empty message when search yields no results", () => {
    render(
      <DataTable
        columns={COLUMNS}
        rows={ROWS}
        rowKey={(r) => r.id}
        searchPlaceholder="Buscar…"
        emptyMessage="Nenhum item encontrado"
      />
    );
    const search = screen.getByPlaceholderText("Buscar…");
    fireEvent.change(search, { target: { value: "zzz" } });
    expect(screen.getByText("Nenhum item encontrado")).toBeInTheDocument();
  });
});
