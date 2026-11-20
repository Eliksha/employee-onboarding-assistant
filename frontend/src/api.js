
import axios from 'axios';

const api = axios.create({
  baseURL: '/api',
  timeout: 45000,
});

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

  payroll: (id) =>
    api.get('/employees/payroll/calendar'),

  chat: (id, question) =>
    api.post('/chat', { employee_id: id, question }),

  history: (id) =>
    api.get('/history', { params: { employee_id: id } }),
};

export default api;
