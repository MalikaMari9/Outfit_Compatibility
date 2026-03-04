import { ReactNode, useEffect, useState } from "react";
import { sanitizeAuthState, syncAuthDbTarget } from "@/lib/auth";

type SessionBoundaryProps = {
  children: ReactNode;
};

const SessionBoundary = ({ children }: SessionBoundaryProps) => {
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let active = true;

    const run = async () => {
      sanitizeAuthState();
      await syncAuthDbTarget();
      if (active) {
        setReady(true);
      }
    };

    run();

    return () => {
      active = false;
    };
  }, []);

  if (!ready) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <p className="text-muted-foreground">Checking session...</p>
      </div>
    );
  }

  return <>{children}</>;
};

export default SessionBoundary;

