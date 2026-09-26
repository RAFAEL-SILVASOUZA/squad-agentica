import { redirect } from "next/navigation";

/**
 * Raiz: redireciona para /dashboard (que está dentro do grupo (dashboard)).
 * O middleware protege as rotas autenticadas.
 */
export default function HomePage() {
  redirect("/dashboard");
}
