import { Suspense } from "react";
import PlanClient from "./client";

function Loading() {
  return (
    <div className="h-screen bg-[#0a0a0a] flex items-center justify-center">
      <div className="w-6 h-6 border-2 border-[#2a2a2a] border-t-[#e8a84c] rounded-full animate-spin" />
    </div>
  );
}

export default function PlanPage() {
  return (
    <Suspense fallback={<Loading />}>
      <PlanClient />
    </Suspense>
  );
}
