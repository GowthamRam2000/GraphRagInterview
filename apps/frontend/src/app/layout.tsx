import type { Metadata } from "next";
import { Google_Sans_Flex, Geist_Mono } from "next/font/google";
import { AppNav } from "@/components/AppNav";
import { PageTransition } from "@/components/PageTransition";
import "./globals.css";

const googleSansFlex = Google_Sans_Flex({
  subsets: ["latin"],
  variable: "--font-sans",
  display: "swap",
  weight: "variable",
});

const geistMono = Geist_Mono({
  subsets: ["latin"],
  variable: "--font-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: "CognizInterview Graph RAG",
  description: "Premium Graph RAG chatbot demo with traceable document intelligence"
};

export default function RootLayout({
  children
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={`${googleSansFlex.variable} ${geistMono.variable}`}>
      <body>
        <AppNav />
        <PageTransition>{children}</PageTransition>
      </body>
    </html>
  );
}
