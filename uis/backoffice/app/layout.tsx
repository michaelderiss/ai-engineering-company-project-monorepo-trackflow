import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "TrackFlow Backoffice",
  description: "Incident analysis console for TrackFlow CX",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <head>
        <AuthGuardScript />
      </head>
      <body>{children}</body>
    </html>
  );
}

/**
 * Returns a <script> tag that protects all backoffice routes except
 * public authentication pages. Runs before any page content.
 */
function AuthGuardScript() {
  const code = `
(function(){
  var p = window.location.pathname;
  if(p==="/login"||p==="/register"||p==="/logout"||p==="/forgot-password"||p==="/reset-password")return;
  var t=null;try{t=localStorage.getItem("trackflow_access_token");}catch(e){}
  if(!t){window.location.href="/login";}
})();
  `;
  // eslint-disable-next-line
  return <script dangerouslySetInnerHTML={{ __html: code }} />;
}
