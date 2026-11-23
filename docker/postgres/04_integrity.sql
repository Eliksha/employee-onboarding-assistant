-- Data integrity for chat history, feedback and escalations (fresh databases).
-- Same end state as backend/migrations/007_data_integrity.py (existing databases); tests check both match
-- backend/services/schema_dictionary.json.

ALTER TABLE public.escalations ADD COLUMN IF NOT EXISTS employee_id text;
ALTER TABLE public.escalations ADD COLUMN IF NOT EXISTS message_id integer;
ALTER TABLE public.feedback ALTER COLUMN message_id SET NOT NULL;

ALTER TABLE ONLY public.messages
    ADD CONSTRAINT messages_employee_id_fkey FOREIGN KEY (employee_id) REFERENCES public.employees(employee_id);
ALTER TABLE ONLY public.messages
    ADD CONSTRAINT messages_found_check CHECK (found IN (0, 1));
ALTER TABLE ONLY public.feedback
    ADD CONSTRAINT feedback_message_id_fkey FOREIGN KEY (message_id) REFERENCES public.messages(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.feedback
    ADD CONSTRAINT feedback_rating_check CHECK (rating IN ('up', 'down'));
ALTER TABLE ONLY public.escalations
    ADD CONSTRAINT escalations_employee_id_fkey FOREIGN KEY (employee_id) REFERENCES public.employees(employee_id);
ALTER TABLE ONLY public.escalations
    ADD CONSTRAINT escalations_message_id_fkey FOREIGN KEY (message_id) REFERENCES public.messages(id) ON DELETE SET NULL;
ALTER TABLE ONLY public.escalations
    ADD CONSTRAINT escalations_status_check CHECK (status IN ('open', 'in_progress', 'resolved', 'closed'));

CREATE INDEX IF NOT EXISTS idx_feedback_message_id ON public.feedback (message_id);
CREATE INDEX IF NOT EXISTS idx_escalations_employee_id ON public.escalations (employee_id);
CREATE INDEX IF NOT EXISTS idx_escalations_message_id ON public.escalations (message_id);
