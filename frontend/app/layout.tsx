import type { Metadata } from "next";
import "./globals.css";
export const metadata: Metadata = {
  title: "OpsFlow AI | Operations workspace",
  description: "Supply-chain disruption analysis and human-approved recovery.",
};
export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
