import axios from 'axios';

// Served behind nginx, which proxies /api/ -> FastAPI on 127.0.0.1:8001.
const api = axios.create({ baseURL: '/api' });

// ---------------------------------------------------------------------------
// Auth / token management (demo login)
// ---------------------------------------------------------------------------
const TOKEN_KEY = 'bankmap_token';
const USER_KEY = 'bankmap_user';

export const saveAuth = (token, user) => {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
};

export const getToken = () => localStorage.getItem(TOKEN_KEY);
export const getUser = () => {
  const u = localStorage.getItem(USER_KEY);
  return u ? JSON.parse(u) : null;
};
export const clearAuth = () => {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
};
export const isAuthenticated = () => !!getToken();

export const login = (email, password) =>
  api.post('/auth/login', { email, password }).then(r => r.data);

// Attach token to every request.
api.interceptors.request.use(config => {
  const token = getToken();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

// On 401, clear auth and bounce to login.
api.interceptors.response.use(
  r => r,
  err => {
    if (err.response?.status === 401) {
      clearAuth();
      window.location.href = '/login';
    }
    return Promise.reject(err);
  }
);

// ---------------------------------------------------------------------------
// Data endpoints
// ---------------------------------------------------------------------------
export const getStates = () => api.get('/states').then(r => r.data);
export const getLGAs = (stateId) => api.get(`/states/${stateId}/lgas`).then(r => r.data);
export const getLGASummary = (lgaId) => api.get(`/lgas/${lgaId}/intelligence/summary`).then(r => r.data);
export const getLGAIntelligence = (lgaId, osmLimit = 3) =>
  api.get(`/lgas/${lgaId}/intelligence?osm_limit=${osmLimit}`).then(r => r.data);
export const getWardIntelligence = (wardId) =>
  api.get(`/wards/${wardId}/intelligence`).then(r => r.data);
export const getWardROI = (wardId, fsoCount) =>
  api.get(`/wards/${wardId}/roi?fso_count=${fsoCount}`).then(r => r.data);

export default api;
