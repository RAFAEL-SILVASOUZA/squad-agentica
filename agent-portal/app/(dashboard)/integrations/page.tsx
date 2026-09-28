import { Suspense } from "react";
import { IntegrationsView } from "@/components/integrations/integrations-view";

export default function IntegrationsPage() {
  return <Suspense fallback={<p>Carregando integrações...</p>}><IntegrationsView /></Suspense>;
}
