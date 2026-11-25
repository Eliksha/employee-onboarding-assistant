-- Synthetic demo reference data only (EMP001-EMP003, leave, assets, payroll, checklist).
-- No chat messages, tickets, feedback or escalations are included.
--
-- PostgreSQL database dump
--


-- Dumped from database version 16.15
-- Dumped by pg_dump version 16.15

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Data for Name: employees; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.employees (employee_id, name, email, department, joining_date, location) VALUES ('EMP001', 'Aarav Sharma', 'aarav.sharma@example.com', 'Technology', '2026-11-02', 'Pune');
INSERT INTO public.employees (employee_id, name, email, department, joining_date, location) VALUES ('EMP002', 'Meera Iyer', 'meera.iyer@example.com', 'Human Resources', '2026-11-09', 'Bengaluru');
INSERT INTO public.employees (employee_id, name, email, department, joining_date, location) VALUES ('EMP003', 'Rohan Verma', 'rohan.verma@example.com', 'Finance', '2026-11-16', 'Hyderabad');


--
-- Data for Name: assets; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.assets (asset_id, employee_id, asset_type, asset_name, status) VALUES ('AST001', 'EMP001', 'Laptop', 'Dell Latitude', 'assigned');
INSERT INTO public.assets (asset_id, employee_id, asset_type, asset_name, status) VALUES ('AST002', 'EMP002', 'Laptop', 'HP EliteBook', 'assigned');
INSERT INTO public.assets (asset_id, employee_id, asset_type, asset_name, status) VALUES ('AST003', 'EMP003', 'Laptop', 'Lenovo ThinkPad', 'assigned');


--
-- Data for Name: checklist; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.checklist (id, phase, task, done) VALUES (1, 'Day 1', 'Collect laptop and ID card', 0);
INSERT INTO public.checklist (id, phase, task, done) VALUES (2, 'Day 1', 'Set up company email and MFA', 0);
INSERT INTO public.checklist (id, phase, task, done) VALUES (3, 'Day 1', 'Meet your manager and onboarding buddy', 0);
INSERT INTO public.checklist (id, phase, task, done) VALUES (4, 'Day 1', 'Log in to NovaConnect and mark attendance', 0);
INSERT INTO public.checklist (id, phase, task, done) VALUES (5, 'Week 1', 'Complete HR documentation', 0);
INSERT INTO public.checklist (id, phase, task, done) VALUES (6, 'Week 1', 'Enrol in group health insurance (within 15 days)', 0);
INSERT INTO public.checklist (id, phase, task, done) VALUES (7, 'Week 1', 'Install NovaVPN from ServiceHub', 0);
INSERT INTO public.checklist (id, phase, task, done) VALUES (8, 'Week 1', 'Complete security awareness training', 0);
INSERT INTO public.checklist (id, phase, task, done) VALUES (9, 'Week 1', 'Submit provisional tax declaration (within 2 weeks)', 0);
INSERT INTO public.checklist (id, phase, task, done) VALUES (10, 'Week 1', 'Review the employee handbook', 0);
INSERT INTO public.checklist (id, phase, task, done) VALUES (11, 'Month 1', 'Complete POSH and code of conduct course', 0);
INSERT INTO public.checklist (id, phase, task, done) VALUES (12, 'Month 1', 'Set 30-60-90 day goals with your manager', 0);
INSERT INTO public.checklist (id, phase, task, done) VALUES (13, 'Month 1', 'Review the holiday list and plan leave', 0);
INSERT INTO public.checklist (id, phase, task, done) VALUES (14, 'Month 1', 'Submit any pending expense claims', 0);
INSERT INTO public.checklist (id, phase, task, done) VALUES (15, 'Month 1', 'Share onboarding feedback with HR', 0);


--
-- Data for Name: checklist_assignments; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.checklist_assignments (employee_id, checklist_id, done) VALUES ('EMP001', 2, 1);
INSERT INTO public.checklist_assignments (employee_id, checklist_id, done) VALUES ('EMP001', 3, 1);
INSERT INTO public.checklist_assignments (employee_id, checklist_id, done) VALUES ('EMP001', 4, 1);
INSERT INTO public.checklist_assignments (employee_id, checklist_id, done) VALUES ('EMP001', 5, 1);
INSERT INTO public.checklist_assignments (employee_id, checklist_id, done) VALUES ('EMP001', 6, 1);
INSERT INTO public.checklist_assignments (employee_id, checklist_id, done) VALUES ('EMP001', 8, 0);
INSERT INTO public.checklist_assignments (employee_id, checklist_id, done) VALUES ('EMP001', 9, 0);
INSERT INTO public.checklist_assignments (employee_id, checklist_id, done) VALUES ('EMP001', 10, 0);
INSERT INTO public.checklist_assignments (employee_id, checklist_id, done) VALUES ('EMP001', 11, 0);
INSERT INTO public.checklist_assignments (employee_id, checklist_id, done) VALUES ('EMP001', 12, 0);
INSERT INTO public.checklist_assignments (employee_id, checklist_id, done) VALUES ('EMP001', 13, 0);
INSERT INTO public.checklist_assignments (employee_id, checklist_id, done) VALUES ('EMP001', 14, 0);
INSERT INTO public.checklist_assignments (employee_id, checklist_id, done) VALUES ('EMP001', 15, 0);
INSERT INTO public.checklist_assignments (employee_id, checklist_id, done) VALUES ('EMP002', 1, 1);
INSERT INTO public.checklist_assignments (employee_id, checklist_id, done) VALUES ('EMP002', 2, 1);
INSERT INTO public.checklist_assignments (employee_id, checklist_id, done) VALUES ('EMP002', 3, 1);
INSERT INTO public.checklist_assignments (employee_id, checklist_id, done) VALUES ('EMP002', 4, 0);
INSERT INTO public.checklist_assignments (employee_id, checklist_id, done) VALUES ('EMP002', 5, 0);
INSERT INTO public.checklist_assignments (employee_id, checklist_id, done) VALUES ('EMP002', 6, 0);
INSERT INTO public.checklist_assignments (employee_id, checklist_id, done) VALUES ('EMP002', 7, 0);
INSERT INTO public.checklist_assignments (employee_id, checklist_id, done) VALUES ('EMP002', 8, 0);
INSERT INTO public.checklist_assignments (employee_id, checklist_id, done) VALUES ('EMP002', 9, 0);
INSERT INTO public.checklist_assignments (employee_id, checklist_id, done) VALUES ('EMP002', 10, 0);
INSERT INTO public.checklist_assignments (employee_id, checklist_id, done) VALUES ('EMP002', 11, 0);
INSERT INTO public.checklist_assignments (employee_id, checklist_id, done) VALUES ('EMP002', 12, 0);
INSERT INTO public.checklist_assignments (employee_id, checklist_id, done) VALUES ('EMP002', 13, 0);
INSERT INTO public.checklist_assignments (employee_id, checklist_id, done) VALUES ('EMP002', 14, 0);
INSERT INTO public.checklist_assignments (employee_id, checklist_id, done) VALUES ('EMP002', 15, 0);
INSERT INTO public.checklist_assignments (employee_id, checklist_id, done) VALUES ('EMP003', 1, 0);
INSERT INTO public.checklist_assignments (employee_id, checklist_id, done) VALUES ('EMP003', 2, 0);
INSERT INTO public.checklist_assignments (employee_id, checklist_id, done) VALUES ('EMP003', 3, 0);
INSERT INTO public.checklist_assignments (employee_id, checklist_id, done) VALUES ('EMP003', 4, 0);
INSERT INTO public.checklist_assignments (employee_id, checklist_id, done) VALUES ('EMP003', 5, 0);
INSERT INTO public.checklist_assignments (employee_id, checklist_id, done) VALUES ('EMP003', 6, 0);
INSERT INTO public.checklist_assignments (employee_id, checklist_id, done) VALUES ('EMP003', 7, 0);
INSERT INTO public.checklist_assignments (employee_id, checklist_id, done) VALUES ('EMP003', 8, 0);
INSERT INTO public.checklist_assignments (employee_id, checklist_id, done) VALUES ('EMP003', 9, 0);
INSERT INTO public.checklist_assignments (employee_id, checklist_id, done) VALUES ('EMP003', 10, 0);
INSERT INTO public.checklist_assignments (employee_id, checklist_id, done) VALUES ('EMP003', 11, 0);
INSERT INTO public.checklist_assignments (employee_id, checklist_id, done) VALUES ('EMP003', 12, 0);
INSERT INTO public.checklist_assignments (employee_id, checklist_id, done) VALUES ('EMP003', 13, 0);
INSERT INTO public.checklist_assignments (employee_id, checklist_id, done) VALUES ('EMP003', 14, 0);
INSERT INTO public.checklist_assignments (employee_id, checklist_id, done) VALUES ('EMP003', 15, 0);
INSERT INTO public.checklist_assignments (employee_id, checklist_id, done) VALUES ('EMP001', 7, 0);
INSERT INTO public.checklist_assignments (employee_id, checklist_id, done) VALUES ('EMP001', 1, 0);


--
-- Data for Name: leave_balances; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.leave_balances (id, employee_id, leave_type, available_days) VALUES (1, 'EMP001', 'Casual Leave', 8);
INSERT INTO public.leave_balances (id, employee_id, leave_type, available_days) VALUES (2, 'EMP001', 'Sick Leave', 6);
INSERT INTO public.leave_balances (id, employee_id, leave_type, available_days) VALUES (3, 'EMP002', 'Casual Leave', 10);
INSERT INTO public.leave_balances (id, employee_id, leave_type, available_days) VALUES (4, 'EMP002', 'Sick Leave', 5);
INSERT INTO public.leave_balances (id, employee_id, leave_type, available_days) VALUES (5, 'EMP003', 'Casual Leave', 7);
INSERT INTO public.leave_balances (id, employee_id, leave_type, available_days) VALUES (6, 'EMP003', 'Sick Leave', 6);


--
-- Data for Name: payroll_calendar; Type: TABLE DATA; Schema: public; Owner: -
--

INSERT INTO public.payroll_calendar (id, payroll_month, payment_date, status) VALUES (1, '2026-11', '2026-11-30', 'scheduled');
INSERT INTO public.payroll_calendar (id, payroll_month, payment_date, status) VALUES (2, '2026-12', '2026-12-31', 'scheduled');


--
-- Name: leave_balances_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.leave_balances_id_seq', 6, true);


--
-- Name: payroll_calendar_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.payroll_calendar_id_seq', 2, true);


--
-- PostgreSQL database dump complete
--


