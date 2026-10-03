import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Call-Help | Safety Command Center",
  description: "AI-powered industrial transit safety. Live monitoring, instant incident response, and safety insights.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className="h-full antialiased">
      <body className="min-h-full">{children}</body>
    </html>
  );
}
