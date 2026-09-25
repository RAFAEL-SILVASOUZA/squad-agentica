/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Produção: build standalone (ver Dockerfile). Em dev, o compose usa `next dev`.
  output: "standalone",
  // O portal fala com a API pela mesma origem (NGINX roteia /api/* pro orchestrator),
  // então não há CORS na prática. Mantido explícito por clareza.
};

export default nextConfig;
