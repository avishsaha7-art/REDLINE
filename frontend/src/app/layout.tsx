import type { Metadata } from "next";
import "./globals.css";
import { AppShell } from "@/components/AppShell";

export const metadata: Metadata = {
  title: "REDLINE — Autonomous Software-Engineering Verification",
  description: "AI-generated code is guilty until proven safe. Executable adversarial verification system with isolated sandboxes and cryptographic evidence receipts.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className="dark">
      <body className="bg-[#09090b] text-[#f4f4f5] antialiased min-h-screen">
        <AppShell>
          {children}
        </AppShell>
      </body>
    </html>
  );
}
