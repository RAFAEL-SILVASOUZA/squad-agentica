import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Agent Portal",
  description: "Portal de pipelines de agentes de IA",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="pt-BR">
      <body>{children}</body>
    </html>
  );
}
