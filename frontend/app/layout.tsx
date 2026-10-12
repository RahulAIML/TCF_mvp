import type { Metadata } from "next";
import { Plus_Jakarta_Sans, Source_Serif_4 } from "next/font/google";
import { AuthProvider } from "@/lib/auth-context";

import "@/app/globals.css";

const sans = Plus_Jakarta_Sans({
  subsets: ["latin"],
  variable: "--font-sans",
  display: "swap",
});

const serif = Source_Serif_4({
  subsets: ["latin"],
  variable: "--font-serif",
  display: "swap",
  preload: false, // Suppress "preloaded but not used" console warnings
});

export const metadata: Metadata = {
  title: "TCF Canada Preparation",
  description: "TCF Canada practice platform with reading, listening, writing, and speaking modules."
};

export default function RootLayout({
  children
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={`${sans.variable} ${serif.variable}`}>
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
