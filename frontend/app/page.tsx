"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { getToken } from "@/lib/api";

// The home page only decides where to send you.
export default function Home() {
  const router = useRouter();
  useEffect(() => {
    router.replace(getToken() ? "/dashboard" : "/login");
  }, [router]);
  return null;
}
