"use client";

import { Suspense, useState, useEffect, useCallback } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useSession } from "next-auth/react";
import { UserPlus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { register } from "@/lib/auth-client";

export default function RegisterPage() {
  return (
    <Suspense>
      <RegisterPageInner />
    </Suspense>
  );
}

function RegisterPageInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { data: session, status } = useSession();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [errors, setErrors] = useState<{
    name?: string;
    email?: string;
    password?: string;
    confirmPassword?: string;
  }>({});
  const [apiError, setApiError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [passwordTouched, setPasswordTouched] = useState(false);

  const callbackUrl = searchParams.get("callbackUrl") ?? "/";

  // Redirect if already authenticated.
  useEffect(() => {
    if (status === "authenticated" && session) {
      router.replace(callbackUrl);
    }
  }, [status, session, router, callbackUrl]);

  const validate = useCallback((): boolean => {
    const errs: {
      name?: string;
      email?: string;
      password?: string;
      confirmPassword?: string;
    } = {};

    if (!name.trim()) {
      errs.name = "Nome é obrigatório";
    }

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

    if (!confirmPassword) {
      errs.confirmPassword = "Confirmação é obrigatória";
    } else if (confirmPassword !== password) {
      errs.confirmPassword = "As senhas não coincidem";
    }

    setErrors(errs);
    return Object.keys(errs).length === 0;
  }, [name, email, password, confirmPassword]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setApiError(null);

    if (!validate()) return;

    setLoading(true);
    const result = await register({ email, password, name });
    setLoading(false);

    if (!result.ok) {
      setApiError(result.error ?? "Falha no registro");
      return;
    }

    router.push(callbackUrl);
    router.refresh();
  };

  const inputStyle = (hasError: boolean): React.CSSProperties => ({
    width: "100%",
    padding: "10px 14px",
    borderRadius: "var(--radius-sm)",
    border: `1px solid ${hasError ? "var(--error)" : "var(--border)"}`,
    background: "var(--bg-elevated)",
    color: "var(--text)",
    fontSize: "13px",
    fontFamily: "var(--font)",
    outline: "none",
    transition: "border-color var(--transition)",
  });

  const labelStyle: React.CSSProperties = {
    display: "block",
    fontSize: "13px",
    fontWeight: 500,
    color: "var(--text)",
    marginBottom: "6px",
  };

  const errorStyle: React.CSSProperties = {
    fontSize: "12px",
    color: "var(--error)",
    margin: "4px 0 0",
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
          Criar conta
        </h1>
        <p
          style={{
            fontSize: "13px",
            color: "var(--text-secondary)",
            margin: "0 0 1.5rem",
          }}
        >
          Registre-se no Agent Portal
        </p>

        {apiError && (
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
            {apiError}
          </div>
        )}

        <form onSubmit={handleSubmit} noValidate>
          <div style={{ marginBottom: "1rem" }}>
            <label htmlFor="name" style={labelStyle}>
              Nome
            </label>
            <input
              id="name"
              type="text"
              autoComplete="name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              aria-describedby={errors.name ? "name-error" : undefined}
              aria-invalid={!!errors.name}
              style={inputStyle(!!errors.name)}
              placeholder="Seu nome"
            />
            {errors.name && (
              <p id="name-error" style={errorStyle}>
                {errors.name}
              </p>
            )}
          </div>

          <div style={{ marginBottom: "1rem" }}>
            <label htmlFor="email" style={labelStyle}>
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
              style={inputStyle(!!errors.email)}
              placeholder="voce@empresa.com"
            />
            {errors.email && (
              <p id="email-error" style={errorStyle}>
                {errors.email}
              </p>
            )}
          </div>

          <div style={{ marginBottom: "1rem" }}>
            <label htmlFor="password" style={labelStyle}>
              Senha
            </label>
            <input
              id="password"
              type="password"
              autoComplete="new-password"
              value={password}
              onChange={(e) => {
                const value = e.target.value;
                setPassword(value);
                if (passwordTouched) {
                  setErrors((current) => ({
                    ...current,
                    password:
                      value.length > 0 && value.length < 8
                        ? "A senha precisa ter pelo menos 8 caracteres"
                        : undefined,
                  }));
                }
              }}
              onBlur={() => {
                setPasswordTouched(true);
                setErrors((current) => ({
                  ...current,
                  password:
                    password.length > 0 && password.length < 8
                      ? "A senha precisa ter pelo menos 8 caracteres"
                      : undefined,
                }));
              }}
              aria-describedby={errors.password ? "password-error" : "password-hint"}
              aria-invalid={!!errors.password}
              style={inputStyle(!!errors.password)}
              placeholder="Mínimo 8 caracteres"
            />
            <p id="password-hint" style={{ ...errorStyle, color: "var(--text-secondary)" }}>
              Mínimo 8 caracteres
            </p>
            {errors.password && (
              <p id="password-error" style={errorStyle}>
                {errors.password}
              </p>
            )}
          </div>

          <div style={{ marginBottom: "1.5rem" }}>
            <label htmlFor="confirmPassword" style={labelStyle}>
              Confirmar senha
            </label>
            <input
              id="confirmPassword"
              type="password"
              autoComplete="new-password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              aria-describedby={
                errors.confirmPassword ? "confirm-password-error" : undefined
              }
              aria-invalid={!!errors.confirmPassword}
              style={inputStyle(!!errors.confirmPassword)}
              placeholder="Repita a senha"
            />
            {errors.confirmPassword && (
              <p id="confirm-password-error" style={errorStyle}>
                {errors.confirmPassword}
              </p>
            )}
          </div>

          <Button
            type="submit"
            variant="primary"
            loading={loading}
            disabled={!!errors.password}
            style={{ width: "100%" }}
          >
            {!loading && <UserPlus size={14} />}
            {loading ? "Criando..." : "Criar conta"}
          </Button>
        </form>

        <p
          style={{
            fontSize: "13px",
            color: "var(--text-secondary)",
            textAlign: "center",
            margin: "1.5rem 0 0",
          }}
        >
          Já tem conta?{" "}
          <a
            href="/login"
            style={{
              color: "var(--accent)",
              textDecoration: "none",
              fontWeight: 500,
            }}
          >
            Entrar
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
