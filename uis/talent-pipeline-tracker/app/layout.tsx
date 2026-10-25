import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "TrackFlow Talent Pipeline Tracker",
  description: "Internal candidate pipeline tool for TrackFlow People and Talent.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <head>
        <AuthGuardScript />
      </head>
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}

/**
 * Inline client-side guard that protects talent pipeline routes.
 * Redirects to backoffice /login if no auth token is found.
 */
function AuthGuardScript() {
  const code = `(function(){var t=null;try{t=localStorage.getItem("trackflow_access_token");}catch(e){}if(!t){window.location.href="/login";}})();`;
  // eslint-disable-next-line
  return <script dangerouslySetInnerHTML={code} />;
}
