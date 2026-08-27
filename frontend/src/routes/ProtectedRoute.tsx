








import { useEffect, useRef } from "react";
import { Navigate, Outlet } from "react-router-dom";
import { useAuthStore } from "../store/authStore";
import { getAccessToken } from "../api/client";

export default function ProtectedRoute() {
  const { isAuthenticated, user, hydrate } = useAuthStore();
  const hasHydratedRef = useRef(false);
  const token = getAccessToken();

  useEffect(() => {
    
    if (token && !user && !hasHydratedRef.current) {
      hasHydratedRef.current = true;
      hydrate().catch(() => {
        
      });
    }
  }, [token, user, hydrate]);

  
  if (!token && !isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  return <Outlet />;
}
