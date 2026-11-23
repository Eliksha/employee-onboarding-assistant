import axios from 'axios';
import { CSRF_HEADER, isAuthEndpoint, isUnsafeMethod } from './auth';

// Same-origin requests: the browser sends the HttpOnly session cookie automatically.
const api = axios.create({
  baseURL: '/api',
  timeout: 45000,
});

// CSRF token for the current session, kept in memory only.
let csrfToken = null;
let unauthorizedHandler = null;

export const setCsrfToken = (token) => { csrfToken = token || null; };
export const setUnauthorizedHandler = (handler) => { unauthorizedHandler = handler; };

api.interceptors.request.use((config) => {
  if (csrfToken && isUnsafeMethod(config.method)) {
    config.headers[CSRF_HEADER] = csrfToken;
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401 && !isAuthEndpoint(error.config?.url) && unauthorizedHandler) {
      unauthorizedHandler();
    }
    return Promise.reject(error);
  },
);

export const authApi = {
  login: (email, password) =>
    api.post('/auth/login', { email, password }),

  logout: () =>
    api.post('/auth/logout'),

  me: () =>
    api.get('/auth/me'),
};

// The backend authorizes every request from the session; the ID in these paths must be the
// signed-in employee's own ID (any other ID is rejected with 403).
export const employeeApi = {
  profile: (id) =>
    api.get(`/employees/${encodeURIComponent(id)}`),

  leave: (id) =>
    api.get(`/employees/${encodeURIComponent(id)}/leave-balances`),

  assets: (id) =>
    api.get(`/employees/${encodeURIComponent(id)}/assets`),

  checklist: (id) =>
    api.get(`/employees/${encodeURIComponent(id)}/checklist`),

  updateChecklist: (id, itemId, done) =>
    api.patch(
      `/employees/${encodeURIComponent(id)}/checklist/${encodeURIComponent(itemId)}`,
      { done }
    ),

  tickets: (id) =>
    api.get(`/employees/${encodeURIComponent(id)}/tickets`),

  createTicket: (id, payload) =>
    api.post(`/employees/${encodeURIComponent(id)}/tickets`, payload),

  // The payroll calendar is company-wide, so no employee ID is sent.
  payroll: () =>
    api.get('/employees/payroll/calendar'),

  chat: (id, question) =>
    api.post('/chat', { employee_id: id, question }),

  history: (id) =>
    api.get('/history', { params: { employee_id: id } }),
};

// Answer feedback and HR/IT escalation (existing backend endpoints; CSRF header added by the interceptor).
export const feedbackApi = {
  rate: (messageId, rating) =>
    api.post('/feedback', { message_id: messageId, rating }),

  escalate: (payload) =>
    api.post('/escalate', payload),
};

export default api;
