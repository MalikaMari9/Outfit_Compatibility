import { ReactNode } from "react";
import { Navigate } from "react-router-dom";
import { getAuthState } from "@/lib/auth";

type ProtectedRouteProps = {
  children: ReactNode;
  requiredRole: "user" | "admin";
};

const ProtectedRoute = ({ children, requiredRole }: ProtectedRouteProps) => {
  const auth = getAuthState();

  if (!auth.isAuthenticated) {
    return <Navigate to="/auth" replace />;
  }

  if (requiredRole === "admin" && auth.role !== "admin") {
    return <Navigate to="/dashboard" replace />;
  }

  if (requiredRole === "user" && auth.role !== "user") {
    return <Navigate to="/admin" replace />;
  }

  return <>{children}</>;
};

export default ProtectedRoute;

