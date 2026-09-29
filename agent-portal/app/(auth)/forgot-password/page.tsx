import Link from "next/link";

export default function ForgotPasswordPage() {
  return (
    <main
      style={{
        minHeight: "100vh",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "1.5rem",
        background: "var(--bg)",
      }}
    >
      <section
        style={{
          width: "100%",
          maxWidth: 400,
          background: "var(--bg-card)",
          border: "1px solid var(--border)",
          borderRadius: "var(--radius)",
          padding: "2rem",
          boxShadow: "var(--shadow)",
        }}
      >
        <h1
          style={{
            fontSize: "1.25rem",
            fontWeight: 600,
            color: "var(--text)",
            margin: "0 0 0.75rem",
          }}
        >
          Esqueci minha senha
        </h1>
        <p
          style={{
            fontSize: "13px",
            lineHeight: 1.6,
            color: "var(--text-secondary)",
            margin: "0 0 1.5rem",
          }}
        >
          Peça ao administrador… para redefinir sua senha.
        </p>
        <Link
          href="/login"
          style={{
            color: "var(--accent)",
            textDecoration: "none",
            fontSize: "13px",
            fontWeight: 500,
          }}
        >
          Voltar para o login
        </Link>
      </section>
    </main>
  );
}
