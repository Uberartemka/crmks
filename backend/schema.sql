--
-- PostgreSQL database dump
--

\restrict yV3UJxzdyCZRIPcmDikq4XYm59cWEAn2jYn5jfamh1FHtJkY1LkoTMVD2Nv7Pjm

-- Dumped from database version 18.4
-- Dumped by pg_dump version 18.4

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: call_logs; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.call_logs (
    id integer NOT NULL,
    user_id integer,
    client_id integer,
    client_name character varying(300),
    call_date character varying(50),
    status character varying(50),
    notes text,
    is_new_registration boolean DEFAULT false,
    created_at character varying(100)
);


--
-- Name: call_logs_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.call_logs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: call_logs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.call_logs_id_seq OWNED BY public.call_logs.id;


--
-- Name: clients; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.clients (
    id integer NOT NULL,
    name character varying(300) NOT NULL,
    bitrix_id character varying(100),
    email character varying(300),
    city character varying(100),
    discount integer DEFAULT 0 NOT NULL,
    status character varying(50) DEFAULT 'active'::character varying,
    created_at character varying(100)
);


--
-- Name: clients_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.clients_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: clients_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.clients_id_seq OWNED BY public.clients.id;


--
-- Name: employee_plans; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.employee_plans (
    id integer NOT NULL,
    user_id integer,
    month integer NOT NULL,
    year integer NOT NULL,
    calls_target integer DEFAULT 0 NOT NULL,
    registrations_target integer DEFAULT 0 NOT NULL,
    created_at character varying(100),
    updated_at character varying(100)
);


--
-- Name: employee_plans_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.employee_plans_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: employee_plans_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.employee_plans_id_seq OWNED BY public.employee_plans.id;


--
-- Name: job_queue; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.job_queue (
    id integer CONSTRAINT tasks_id_not_null NOT NULL,
    task_type character varying(100) CONSTRAINT tasks_task_type_not_null NOT NULL,
    status character varying(50) DEFAULT 'pending'::character varying CONSTRAINT tasks_status_not_null NOT NULL,
    payload text CONSTRAINT tasks_payload_not_null NOT NULL,
    retries integer DEFAULT 0 CONSTRAINT tasks_retries_not_null NOT NULL,
    max_retries integer DEFAULT 3 CONSTRAINT tasks_max_retries_not_null NOT NULL,
    error_message text,
    created_at character varying(100) CONSTRAINT tasks_created_at_not_null NOT NULL,
    updated_at character varying(100) CONSTRAINT tasks_updated_at_not_null NOT NULL
);


--
-- Name: parsed_leads; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.parsed_leads (
    id integer NOT NULL,
    name character varying(300) NOT NULL,
    category character varying(200),
    city character varying(100),
    contacts text,
    need_description text,
    query character varying(200),
    region character varying(100),
    status character varying(50) DEFAULT 'новый'::character varying,
    assigned_to integer,
    call_count integer DEFAULT 0,
    created_at character varying(100),
    updated_at character varying(100),
    CONSTRAINT parsed_leads_status_check CHECK (((status)::text = ANY ((ARRAY['новый'::character varying, 'горячий'::character varying, 'назначен'::character varying, 'в_работе'::character varying, 'закрыт'::character varying, 'отказ'::character varying])::text[])))
);


--
-- Name: parsed_leads_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.parsed_leads_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: parsed_leads_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.parsed_leads_id_seq OWNED BY public.parsed_leads.id;


--
-- Name: proposal_items; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.proposal_items (
    id integer NOT NULL,
    proposal_id integer,
    sku_id integer,
    qty integer DEFAULT 1 NOT NULL,
    price_base numeric(12,2) DEFAULT 0 NOT NULL,
    discount_item integer DEFAULT 0,
    price_final numeric(12,2) DEFAULT 0 NOT NULL
);


--
-- Name: proposal_items_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.proposal_items_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: proposal_items_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.proposal_items_id_seq OWNED BY public.proposal_items.id;


--
-- Name: proposals; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.proposals (
    id integer NOT NULL,
    client_id integer,
    title character varying(300),
    total_amount numeric(14,2) DEFAULT 0,
    discount_global integer DEFAULT 0,
    status character varying(50) DEFAULT 'draft'::character varying,
    email_sent boolean DEFAULT false,
    created_at character varying(100),
    updated_at character varying(100)
);


--
-- Name: proposals_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.proposals_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: proposals_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.proposals_id_seq OWNED BY public.proposals.id;


--
-- Name: sku_catalog; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.sku_catalog (
    id integer NOT NULL,
    sku character varying(200) NOT NULL,
    category character varying(100),
    gost character varying(50),
    d_inner numeric(10,2),
    d_outer numeric(10,2),
    b_width numeric(10,2),
    type character varying(300),
    brand character varying(50),
    stock character varying(100),
    price numeric(12,2) DEFAULT 0 NOT NULL,
    img character varying(300),
    created_at character varying(100)
);


--
-- Name: sku_catalog_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.sku_catalog_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: sku_catalog_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.sku_catalog_id_seq OWNED BY public.sku_catalog.id;


--
-- Name: tasks_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.tasks_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: tasks_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.tasks_id_seq OWNED BY public.job_queue.id;


--
-- Name: users; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.users (
    id integer NOT NULL,
    username character varying(100) NOT NULL,
    password_hash character varying(256) NOT NULL,
    name character varying(200) NOT NULL,
    role character varying(50) DEFAULT 'employee'::character varying NOT NULL,
    created_at character varying(100)
);


--
-- Name: users_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.users_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: users_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.users_id_seq OWNED BY public.users.id;


--
-- Name: call_logs id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.call_logs ALTER COLUMN id SET DEFAULT nextval('public.call_logs_id_seq'::regclass);


--
-- Name: clients id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.clients ALTER COLUMN id SET DEFAULT nextval('public.clients_id_seq'::regclass);


--
-- Name: employee_plans id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.employee_plans ALTER COLUMN id SET DEFAULT nextval('public.employee_plans_id_seq'::regclass);


--
-- Name: job_queue id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.job_queue ALTER COLUMN id SET DEFAULT nextval('public.tasks_id_seq'::regclass);


--
-- Name: parsed_leads id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.parsed_leads ALTER COLUMN id SET DEFAULT nextval('public.parsed_leads_id_seq'::regclass);


--
-- Name: proposal_items id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.proposal_items ALTER COLUMN id SET DEFAULT nextval('public.proposal_items_id_seq'::regclass);


--
-- Name: proposals id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.proposals ALTER COLUMN id SET DEFAULT nextval('public.proposals_id_seq'::regclass);


--
-- Name: sku_catalog id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sku_catalog ALTER COLUMN id SET DEFAULT nextval('public.sku_catalog_id_seq'::regclass);


--
-- Name: users id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users ALTER COLUMN id SET DEFAULT nextval('public.users_id_seq'::regclass);


--
-- Name: call_logs call_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.call_logs
    ADD CONSTRAINT call_logs_pkey PRIMARY KEY (id);


--
-- Name: clients clients_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.clients
    ADD CONSTRAINT clients_pkey PRIMARY KEY (id);


--
-- Name: employee_plans employee_plans_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.employee_plans
    ADD CONSTRAINT employee_plans_pkey PRIMARY KEY (id);


--
-- Name: employee_plans employee_plans_user_id_month_year_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.employee_plans
    ADD CONSTRAINT employee_plans_user_id_month_year_key UNIQUE (user_id, month, year);


--
-- Name: parsed_leads parsed_leads_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.parsed_leads
    ADD CONSTRAINT parsed_leads_pkey PRIMARY KEY (id);


--
-- Name: proposal_items proposal_items_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.proposal_items
    ADD CONSTRAINT proposal_items_pkey PRIMARY KEY (id);


--
-- Name: proposals proposals_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.proposals
    ADD CONSTRAINT proposals_pkey PRIMARY KEY (id);


--
-- Name: sku_catalog sku_catalog_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sku_catalog
    ADD CONSTRAINT sku_catalog_pkey PRIMARY KEY (id);


--
-- Name: sku_catalog sku_catalog_sku_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.sku_catalog
    ADD CONSTRAINT sku_catalog_sku_key UNIQUE (sku);


--
-- Name: job_queue tasks_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.job_queue
    ADD CONSTRAINT tasks_pkey PRIMARY KEY (id);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: users users_username_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_username_key UNIQUE (username);


--
-- Name: call_logs call_logs_client_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.call_logs
    ADD CONSTRAINT call_logs_client_id_fkey FOREIGN KEY (client_id) REFERENCES public.clients(id) ON DELETE SET NULL;


--
-- Name: call_logs call_logs_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.call_logs
    ADD CONSTRAINT call_logs_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: employee_plans employee_plans_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.employee_plans
    ADD CONSTRAINT employee_plans_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: parsed_leads parsed_leads_assigned_to_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.parsed_leads
    ADD CONSTRAINT parsed_leads_assigned_to_fkey FOREIGN KEY (assigned_to) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: proposal_items proposal_items_proposal_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.proposal_items
    ADD CONSTRAINT proposal_items_proposal_id_fkey FOREIGN KEY (proposal_id) REFERENCES public.proposals(id) ON DELETE CASCADE;


--
-- Name: proposal_items proposal_items_sku_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.proposal_items
    ADD CONSTRAINT proposal_items_sku_id_fkey FOREIGN KEY (sku_id) REFERENCES public.sku_catalog(id) ON DELETE CASCADE;


--
-- Name: proposals proposals_client_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.proposals
    ADD CONSTRAINT proposals_client_id_fkey FOREIGN KEY (client_id) REFERENCES public.clients(id) ON DELETE SET NULL;


--
-- PostgreSQL database dump complete
--

\unrestrict yV3UJxzdyCZRIPcmDikq4XYm59cWEAn2jYn5jfamh1FHtJkY1LkoTMVD2Nv7Pjm

