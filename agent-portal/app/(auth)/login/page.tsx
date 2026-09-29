"use client";

import { Suspense, useState, useEffect, useCallback } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { signIn } from "next-auth/react";
import { useSession } from "next-auth/react";
import { LogIn } from "lucide-react";
import { Button } from "@/components/ui/button";

export default function LoginPage() {
  return (
    <Suspense>
      <LoginPageInner />
    </Suspense>
  );
}

function LoginPageInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { data: session, status } = useSession();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [errors, setErrors] = useState<{ email?: string; password?: string }>({});
  const [apiError, setApiError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const callbackUrl = searchParams.get("callbackUrl") ?? "/";
  const urlError = searchParams.get("error");

  // Redirect if already authenticated.
  useEffect(() => {
    // Sessão marcada como expirada (refresh recusado) ainda vem como
    // "authenticated": voltar para a app criaria um loop com o middleware.
    if (status === "authenticated" && session && !session.authError) {
      router.replace(callbackUrl);
    }
  }, [status, session, router, callbackUrl]);

  const validate = useCallback((): boolean => {
    const errs: { email?: string; password?: string } = {};
    if (!email.trim()) {
      errs.email = "Email é obrigatório";
    } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      errs.email = "Email inválido";
    }
    if (!password) {
      errs.password = "Senha é obrigatória";
    } else if (password.length < 8) {
      errs.password = "Senha deve ter no mínimo 8 caracteres";
    }
    setErrors(errs);
    return Object.keys(errs).length === 0;
  }, [email, password]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setApiError(null);

    if (!validate()) return;

    setLoading(true);
    const result = await signIn("credentials", {
      email,
      password,
      redirect: false,
    });
    setLoading(false);

    if (result?.error) {
      setApiError("Credenciais inválidas. Verifique seu e-mail e senha.");
      return;
    }

    router.push(callbackUrl);
    router.refresh();
  };

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
      <div
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
            margin: "0 0 0.5rem",
          }}
        >
          Entrar
        </h1>
        <p
          style={{
            fontSize: "13px",
            color: "var(--text-secondary)",
            margin: "0 0 1.5rem",
          }}
        >
          Acesse o Agent Portal
        </p>

        {(apiError || urlError) && (
          <div
            role="alert"
            style={{
              padding: "10px 14px",
              borderRadius: "var(--radius-sm)",
              background: "rgba(248, 113, 113, 0.1)",
              border: "1px solid var(--error)",
              color: "var(--error)",
              fontSize: "13px",
              marginBottom: "1rem",
            }}
          >
            {apiError ??
              (urlError === "session_expired"
                ? "Sua sessão expirou. Entre novamente."
                : "Falha na autenticação")}
          </div>
        )}

        <form onSubmit={handleSubmit} noValidate>
          <div style={{ marginBottom: "1rem" }}>
            <label
              htmlFor="email"
              style={{
                display: "block",
                fontSize: "13px",
                fontWeight: 500,
                color: "var(--text)",
                marginBottom: "6px",
              }}
            >
              E-mail
            </label>
            <input
              id="email"
              type="email"
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              aria-describedby={errors.email ? "email-error" : undefined}
              aria-invalid={!!errors.email}
              style={{
                width: "100%",
                padding: "10px 14px",
                borderRadius: "var(--radius-sm)",
                border: `1px solid ${errors.email ? "var(--error)" : "var(--border)"}`,
                background: "var(--bg-elevated)",
                color: "var(--text)",
                fontSize: "13px",
                fontFamily: "var(--font)",
                outline: "none",
                transition: "border-color var(--transition)",
              }}
              placeholder="voce@empresa.com"
            />
            {errors.email && (
              <p
                id="email-error"
                style={{
                  fontSize: "12px",
                  color: "var(--error)",
                  margin: "4px 0 0",
                }}
              >
                {errors.email}
              </p>
            )}
          </div>

          <div style={{ marginBottom: "1.5rem" }}>
            <label
              htmlFor="password"
              style={{
                display: "block",
                fontSize: "13px",
                fontWeight: 500,
                color: "var(--text)",
                marginBottom: "6px",
              }}
            >
              Senha
            </label>
            <input
              id="password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              aria-describedby={errors.password ? "password-error" : undefined}
              aria-invalid={!!errors.password}
              style={{
                width: "100%",
                padding: "10px 14px",
                borderRadius: "var(--radius-sm)",
                border: `1px solid ${errors.password ? "var(--error)" : "var(--border)"}`,
                background: "var(--bg-elevated)",
                color: "var(--text)",
                fontSize: "13px",
                fontFamily: "var(--font)",
                outline: "none",
                transition: "border-color var(--transition)",
              }}
              placeholder="••••••••"
            />
            {errors.password && (
              <p
                id="password-error"
                style={{
                  fontSize: "12px",
                  color: "var(--error)",
                  margin: "4px 0 0",
                }}
              >
                {errors.password}
              </p>
            )}
          </div>

          <Button
            type="submit"
            variant="primary"
            loading={loading}
            style={{ width: "100%" }}
          >
            {!loading && <LogIn size={14} />}
            {loading ? "Entrando..." : "Entrar"}
          </Button>
        </form>

        <p
          style={{
            fontSize: "13px",
            color: "var(--text-secondary)",
            textAlign: "right",
            margin: "0.75rem 0 0",
          }}
        >
          <a
            href="/forgot-password"
            style={{ color: "var(--accent)", textDecoration: "none", fontWeight: 500 }}
          >
            Esqueci?
          </a>
        </p>

        <p
          style={{
            fontSize: "13px",
            color: "var(--text-secondary)",
            textAlign: "center",
            margin: "1.5rem 0 0",
          }}
        >
          Não tem conta?{" "}
          <a
            href="/register"
            style={{
              color: "var(--accent)",
              textDecoration: "none",
              fontWeight: 500,
            }}
          >
            Criar conta
          </a>
        </p>
      </div>

      <style>{`
        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
      `}</style>
    </main>
  );
}
