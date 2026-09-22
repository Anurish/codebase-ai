import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Codebase AI",
  description: "AI-powered codebase review and Q&A"
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return <html lang="en"><body>{children}</body></html>;
}