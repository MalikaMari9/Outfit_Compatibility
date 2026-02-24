const DEFAULT_API_URL = "http://localhost:8001";

export const API_BASE_URL = import.meta.env.VITE_API_URL || DEFAULT_API_URL;

export const apiUrl = (path: string) => {
  if (path.startsWith("http://") || path.startsWith("https://")) {
    return path;
  }
  const normalized = path.startsWith("/") ? path : `/${path}`;
  return `${API_BASE_URL}${normalized}`;
};

export const getAuthHeader = () => {
  const token = localStorage.getItem("token");
  return token ? { Authorization: `Bearer ${token}` } : {};
};
