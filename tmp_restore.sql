--
-- PostgreSQL database dump
--

\restrict iz9oIflLZWclnEG5ItRg9yjWJdzBe2qefZFJdJmK1YcJUHegaJLCYHhFBl5onnQ

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
-- Name: calendar_events; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.calendar_events (
    id integer NOT NULL,
    title character varying(300) NOT NULL,
    description text,
    kind character varying(50) DEFAULT 'meeting'::character varying,
    start timestamp without time zone NOT NULL,
    "end" timestamp without time zone,
    all_day boolean DEFAULT false,
    location character varying(300),
    client_id integer,
    color character varying(20) DEFAULT 'blue'::character varying,
    created_at character varying(100),
    updated_at character varying(100),
    user_id integer,
    created_by integer
);


ALTER TABLE public.calendar_events OWNER TO postgres;

--
-- Name: calendar_events_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.calendar_events_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.calendar_events_id_seq OWNER TO postgres;

--
-- Name: calendar_events_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.calendar_events_id_seq OWNED BY public.calendar_events.id;


--
-- Name: call_logs; Type: TABLE; Schema: public; Owner: postgres
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
    created_at character varying(100),
    lead_id integer,
    from_number character varying(50),
    to_number character varying(50),
    direction character varying(20),
    duration integer,
    recording_url text,
    bitrix_call_id character varying(100),
    updated_at character varying(100),
    transcript text,
    ai_score integer,
    ai_analysis text
);


ALTER TABLE public.call_logs OWNER TO postgres;

--
-- Name: call_logs_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.call_logs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.call_logs_id_seq OWNER TO postgres;

--
-- Name: call_logs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.call_logs_id_seq OWNED BY public.call_logs.id;


--
-- Name: clients; Type: TABLE; Schema: public; Owner: postgres
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


ALTER TABLE public.clients OWNER TO postgres;

--
-- Name: clients_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.clients_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.clients_id_seq OWNER TO postgres;

--
-- Name: clients_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.clients_id_seq OWNED BY public.clients.id;


--
-- Name: daily_plans; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.daily_plans (
    id integer NOT NULL,
    user_id integer,
    date date NOT NULL,
    plan_data text NOT NULL,
    updated_at character varying(100)
);


ALTER TABLE public.daily_plans OWNER TO postgres;

--
-- Name: daily_plans_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.daily_plans_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.daily_plans_id_seq OWNER TO postgres;

--
-- Name: daily_plans_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.daily_plans_id_seq OWNED BY public.daily_plans.id;


--
-- Name: employee_plans; Type: TABLE; Schema: public; Owner: postgres
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


ALTER TABLE public.employee_plans OWNER TO postgres;

--
-- Name: employee_plans_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.employee_plans_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.employee_plans_id_seq OWNER TO postgres;

--
-- Name: employee_plans_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.employee_plans_id_seq OWNED BY public.employee_plans.id;


--
-- Name: job_queue; Type: TABLE; Schema: public; Owner: postgres
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


ALTER TABLE public.job_queue OWNER TO postgres;

--
-- Name: notes; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.notes (
    id integer NOT NULL,
    user_id integer,
    title character varying(300),
    content text NOT NULL,
    color character varying(20) DEFAULT 'yellow'::character varying,
    created_at character varying(100),
    updated_at character varying(100),
    pinned integer DEFAULT 0,
    tags text,
    client_id integer
);


ALTER TABLE public.notes OWNER TO postgres;

--
-- Name: notes_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.notes_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.notes_id_seq OWNER TO postgres;

--
-- Name: notes_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.notes_id_seq OWNED BY public.notes.id;


--
-- Name: parsed_leads; Type: TABLE; Schema: public; Owner: postgres
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


ALTER TABLE public.parsed_leads OWNER TO postgres;

--
-- Name: parsed_leads_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.parsed_leads_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.parsed_leads_id_seq OWNER TO postgres;

--
-- Name: parsed_leads_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.parsed_leads_id_seq OWNED BY public.parsed_leads.id;


--
-- Name: proposal_items; Type: TABLE; Schema: public; Owner: postgres
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


ALTER TABLE public.proposal_items OWNER TO postgres;

--
-- Name: proposal_items_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.proposal_items_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.proposal_items_id_seq OWNER TO postgres;

--
-- Name: proposal_items_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.proposal_items_id_seq OWNED BY public.proposal_items.id;


--
-- Name: proposals; Type: TABLE; Schema: public; Owner: postgres
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
    updated_at character varying(100),
    created_by integer,
    accepted_at character varying(100)
);


ALTER TABLE public.proposals OWNER TO postgres;

--
-- Name: proposals_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.proposals_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.proposals_id_seq OWNER TO postgres;

--
-- Name: proposals_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.proposals_id_seq OWNED BY public.proposals.id;


--
-- Name: sku_catalog; Type: TABLE; Schema: public; Owner: postgres
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


ALTER TABLE public.sku_catalog OWNER TO postgres;

--
-- Name: sku_catalog_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.sku_catalog_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.sku_catalog_id_seq OWNER TO postgres;

--
-- Name: sku_catalog_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.sku_catalog_id_seq OWNED BY public.sku_catalog.id;


--
-- Name: tasks; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.tasks (
    id integer CONSTRAINT tasks_id_not_null1 NOT NULL,
    assigned_to integer,
    created_by character varying(100) DEFAULT 'ai_agent'::character varying,
    lead_id integer,
    call_id integer,
    title character varying(300) NOT NULL,
    description text,
    priority character varying(50) DEFAULT 'normal'::character varying,
    due_date character varying(100),
    status character varying(50) DEFAULT 'open'::character varying,
    source character varying(100) DEFAULT 'manual'::character varying,
    created_at character varying(100),
    completed_at character varying(100),
    updated_at character varying(100),
    estimated_minutes integer
);


ALTER TABLE public.tasks OWNER TO postgres;

--
-- Name: tasks_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.tasks_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.tasks_id_seq OWNER TO postgres;

--
-- Name: tasks_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.tasks_id_seq OWNED BY public.job_queue.id;


--
-- Name: tasks_id_seq1; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.tasks_id_seq1
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.tasks_id_seq1 OWNER TO postgres;

--
-- Name: tasks_id_seq1; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.tasks_id_seq1 OWNED BY public.tasks.id;


--
-- Name: users; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.users (
    id integer NOT NULL,
    username character varying(100) NOT NULL,
    password_hash character varying(256) NOT NULL,
    name character varying(200) NOT NULL,
    role character varying(50) DEFAULT 'employee'::character varying NOT NULL,
    created_at character varying(100)
);


ALTER TABLE public.users OWNER TO postgres;

--
-- Name: users_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.users_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.users_id_seq OWNER TO postgres;

--
-- Name: users_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.users_id_seq OWNED BY public.users.id;


--
-- Name: calendar_events id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.calendar_events ALTER COLUMN id SET DEFAULT nextval('public.calendar_events_id_seq'::regclass);


--
-- Name: call_logs id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.call_logs ALTER COLUMN id SET DEFAULT nextval('public.call_logs_id_seq'::regclass);


--
-- Name: clients id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.clients ALTER COLUMN id SET DEFAULT nextval('public.clients_id_seq'::regclass);


--
-- Name: daily_plans id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.daily_plans ALTER COLUMN id SET DEFAULT nextval('public.daily_plans_id_seq'::regclass);


--
-- Name: employee_plans id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.employee_plans ALTER COLUMN id SET DEFAULT nextval('public.employee_plans_id_seq'::regclass);


--
-- Name: job_queue id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.job_queue ALTER COLUMN id SET DEFAULT nextval('public.tasks_id_seq'::regclass);


--
-- Name: notes id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.notes ALTER COLUMN id SET DEFAULT nextval('public.notes_id_seq'::regclass);


--
-- Name: parsed_leads id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.parsed_leads ALTER COLUMN id SET DEFAULT nextval('public.parsed_leads_id_seq'::regclass);


--
-- Name: proposal_items id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.proposal_items ALTER COLUMN id SET DEFAULT nextval('public.proposal_items_id_seq'::regclass);


--
-- Name: proposals id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.proposals ALTER COLUMN id SET DEFAULT nextval('public.proposals_id_seq'::regclass);


--
-- Name: sku_catalog id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.sku_catalog ALTER COLUMN id SET DEFAULT nextval('public.sku_catalog_id_seq'::regclass);


--
-- Name: tasks id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.tasks ALTER COLUMN id SET DEFAULT nextval('public.tasks_id_seq1'::regclass);


--
-- Name: users id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.users ALTER COLUMN id SET DEFAULT nextval('public.users_id_seq'::regclass);


--
-- Data for Name: calendar_events; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.calendar_events (id, title, description, kind, start, "end", all_day, location, client_id, color, created_at, updated_at, user_id, created_by) FROM stdin;
\.


--
-- Data for Name: call_logs; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.call_logs (id, user_id, client_id, client_name, call_date, status, notes, is_new_registration, created_at, lead_id, from_number, to_number, direction, duration, recording_url, bitrix_call_id, updated_at, transcript, ai_score, ai_analysis) FROM stdin;
\.


--
-- Data for Name: clients; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.clients (id, name, bitrix_id, email, city, discount, status, created_at) FROM stdin;
1	ООО "АГРОЭКО"	BX_1245	snab@agroeco.ru	Воронеж	15	active	2026-05-28T22:56:59.434385
2	ООО "ЭКОНИВА-ЧЕРНОЗЕМЬЕ"	BX_3312	zakup@econiva.ru	Воронеж	10	active	2026-05-28T22:56:59.434385
3	АПХ "МИРАТОРГ"	BX_8821	supply@miratorg.ru	Орёл	5	active	2026-05-28T22:56:59.434385
4	ГК "РУСАГРО"	BX_9901	tender@rusagro.ru	Москва	0	new	2026-05-28T22:56:59.434385
5	ООО "Воронежский Элеватор"	BX_1122	main@vorelev.ru	Воронеж	20	vip	2026-05-28T22:56:59.434385
6	Калачеевский Элеватор	\N	\N	\N	0	active	2026-05-29T04:15:16.879904
\.


--
-- Data for Name: daily_plans; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.daily_plans (id, user_id, date, plan_data, updated_at) FROM stdin;
1	1	2026-06-02	{"greeting": "Отличный день для новых сделок!", "focus": "Сфокусируйся на горячих лидах", "schedule": [{"time": "09:00", "type": "call", "title": "Обзвон горячих лидов", "lead_id": null, "task_id": null, "duration_min": 60}], "calls_target": 15, "kp_target": 1, "tip": "Начни день с самых сложных звонков"}	2026-06-02T22:54:27.501447
13	8	2026-06-05	{"greeting": "Отличный день для новых сделок!", "focus": "Сфокусируйся на горячих лидах", "schedule": [{"time": "09:00", "type": "call", "title": "Обзвон горячих лидов", "lead_id": null, "task_id": null, "duration_min": 60}], "calls_target": 15, "kp_target": 1, "tip": "Начни день с самых сложных звонков"}	2026-06-05T08:02:22.571197
3	1	2026-06-03	{"greeting": "Отличный день для новых сделок!", "focus": "Сфокусируйся на горячих лидах", "schedule": [{"time": "09:00", "type": "call", "title": "Обзвон горячих лидов", "lead_id": null, "task_id": null, "duration_min": 60}], "calls_target": 15, "kp_target": 1, "tip": "Начни день с самых сложных звонков"}	2026-06-03T03:20:03.839955
10	5	2026-06-05	{"greeting": "Отличный день для новых сделок!", "focus": "Сфокусируйся на горячих лидах", "schedule": [{"time": "09:00", "type": "call", "title": "Обзвон горячих лидов", "lead_id": null, "task_id": null, "duration_min": 60}], "calls_target": 15, "kp_target": 1, "tip": "Начни день с самых сложных звонков"}	2026-06-05T08:00:00.096972
11	6	2026-06-05	{"greeting": "Отличный день для новых сделок!", "focus": "Сфокусируйся на горячих лидах", "schedule": [{"time": "09:00", "type": "call", "title": "Обзвон горячих лидов", "lead_id": null, "task_id": null, "duration_min": 60}], "calls_target": 15, "kp_target": 1, "tip": "Начни день с самых сложных звонков"}	2026-06-05T08:00:50.828672
12	7	2026-06-05	{"greeting": "Отличный день для новых сделок!", "focus": "Сфокусируйся на горячих лидах", "schedule": [{"time": "09:00", "type": "call", "title": "Обзвон горячих лидов", "lead_id": null, "task_id": null, "duration_min": 60}], "calls_target": 15, "kp_target": 1, "tip": "Начни день с самых сложных звонков"}	2026-06-05T08:01:22.157253
\.


--
-- Data for Name: employee_plans; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.employee_plans (id, user_id, month, year, calls_target, registrations_target, created_at, updated_at) FROM stdin;
1	1	6	2026	200	20	2026-06-02T02:59:57.555687	2026-06-02T02:59:57.555687
\.


--
-- Data for Name: job_queue; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.job_queue (id, task_type, status, payload, retries, max_retries, error_message, created_at, updated_at) FROM stdin;
13	crm_lead	completed	{"event_type": "TEST_EVENT", "deal_id": 123, "raw_data": {"ID": 123}}	0	3	\N	2026-06-03T02:02:16.716996	2026-06-03T02:02:18.893455
1	crm_lead	completed	{"event_type": "TEST_EVENT", "deal_id": 123, "raw_data": {"ID": 123}}	0	3	\N	2026-06-01T20:00:04.003376	2026-06-01T20:00:06.864451
2	crm_lead	completed	{"event_type": "TEST_EVENT", "deal_id": 123, "raw_data": {"ID": 123}}	0	3	\N	2026-06-01T20:02:51.952755	2026-06-01T20:02:54.046185
3	1c_sync	completed	{"sku": "TEST", "new_stock": 1, "new_price": 1.0}	0	3	\N	2026-06-01T22:01:46.496417	2026-06-01T22:01:50.175317
14	crm_lead	completed	{"event_type": "TEST_EVENT", "deal_id": 123, "raw_data": {"ID": 123}}	0	3	\N	2026-06-03T03:34:34.999264	2026-06-03T03:34:37.210990
4	crm_lead	completed	{"event_type": "TEST_EVENT", "deal_id": 123, "raw_data": {"ID": 123}}	0	3	\N	2026-06-02T02:04:36.725449	2026-06-02T02:04:39.722730
5	crm_lead	completed	{"event_type": "TEST_EVENT", "deal_id": 123, "raw_data": {"ID": 123}}	0	3	\N	2026-06-02T02:08:04.910323	2026-06-02T02:08:07.518700
6	crm_lead	completed	{"event_type": "TEST_EVENT", "deal_id": 123, "raw_data": {"ID": 123}}	0	3	\N	2026-06-02T02:11:30.436472	2026-06-02T02:11:33.230786
15	crm_lead	completed	{"event_type": "TEST_EVENT", "deal_id": 123, "raw_data": {"ID": 123}}	0	3	\N	2026-06-03T03:44:08.431674	2026-06-03T03:44:12.075435
7	crm_lead	completed	{"event_type": "TEST_EVENT", "deal_id": 123, "raw_data": {"ID": 123}}	0	3	\N	2026-06-02T02:14:48.629776	2026-06-02T02:14:51.070647
8	crm_lead	completed	{"event_type": "TEST_EVENT", "deal_id": 123, "raw_data": {"ID": 123}}	0	3	\N	2026-06-02T02:17:07.727373	2026-06-02T02:17:10.799018
9	crm_lead	completed	{"event_type": "TEST_EVENT", "deal_id": 123, "raw_data": {"ID": 123}}	0	3	\N	2026-06-03T01:05:40.173580	2026-06-03T01:05:43.184371
16	crm_lead	completed	{"event_type": "TEST_EVENT", "deal_id": 123, "raw_data": {"ID": 123}}	0	3	\N	2026-06-03T03:45:08.018481	2026-06-03T03:45:11.645062
10	crm_lead	completed	{"event_type": "TEST_EVENT", "deal_id": 123, "raw_data": {"ID": 123}}	0	3	\N	2026-06-03T01:24:25.849376	2026-06-03T01:24:28.624435
11	crm_lead	completed	{"event_type": "TEST_EVENT", "deal_id": 123, "raw_data": {"ID": 123}}	0	3	\N	2026-06-03T01:45:37.571696	2026-06-03T01:45:40.785746
12	crm_lead	completed	{"event_type": "TEST_EVENT", "deal_id": 123, "raw_data": {"ID": 123}}	0	3	\N	2026-06-03T01:58:51.013137	2026-06-03T01:58:53.208999
\.


--
-- Data for Name: notes; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.notes (id, user_id, title, content, color, created_at, updated_at, pinned, tags, client_id) FROM stdin;
4	1	Мираторг принял предложение!		yellow	2026-06-02T04:29:58.163035	2026-06-02T04:29:58.163035	0	[]	\N
5	1	Smoke note	Hello from smoke test	yellow	2026-06-03T01:26:41.206917	2026-06-03T01:26:41.206917	0	["smoke"]	\N
\.


--
-- Data for Name: parsed_leads; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.parsed_leads (id, name, category, city, contacts, need_description, query, region, status, assigned_to, call_count, created_at, updated_at) FROM stdin;
3	Калачеевский Элеватор	Элеватор, Сушилки	Калач	+7 (47363) 2-14-55 · kalachel.ru	Двухрядные сферические подшипники для вентиляторов зерносушилок.	элеватор	Воронеж	в_работе	6	0	2026-05-28T22:56:59.757348	2026-05-29T00:12:37.920137
4	Липецкхлебмакаронпром	Элеватор, Мельница	Липецк	+7 (4742) 28-04-12 · lhm.ru	Премиум подшипники HHB 6205, зазор C3, радиальные.	элеватор	Липецк	в_работе	6	0	2026-05-28T22:56:59.757348	2026-05-29T00:12:39.233943
6	Павловск Неруд (Карьероуправление)	Добыча щебня, Карьер	Павловск	+7 (47362) 2-15-51 · pavlovskgranit.ru	Вибростойкие подшипники HHB T41A (22316) для инерционных грохотов. Ударная нагрузка.	карьер	Воронеж	в_работе	6	0	2026-05-28T22:56:59.757348	2026-05-29T03:41:41.073563
1	Воронежский Мукомольный Комбинат	Элеватор, Хранение	Воронеж	+7 (473) 255-44-12 · vormuk.ru	Корпусные узлы UCP208 для приводных барабанов норий. Высокая агропыль.	элеватор	Воронеж	в_работе	6	0	2026-05-28T22:56:59.757348	2026-05-29T00:00:04.062332
5	Грибановский Сахарный Завод	Сахарный завод, Пищевка	Грибановка	+7 (47348) 3-01-22	Подшипники конвейерной ленты сырого жома, нержавеющие корпуса HHB-SS.	сахарный завод	Воронеж	в_работе	6	0	2026-05-28T22:56:59.757348	2026-05-29T00:00:05.292322
2	АГРОЭКО-Восток (Элеваторный Хаб)	Элеватор, Зернохранилище	Воронеж	+7 (473) 200-11-11 · agroeco.ru	Самоустанавливающиеся подшипники серии UC, натяжные узлы UCF206.	элеватор	Воронеж	в_работе	6	0	2026-05-28T22:56:59.757348	2026-05-29T00:00:06.393143
\.


--
-- Data for Name: proposal_items; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.proposal_items (id, proposal_id, sku_id, qty, price_base, discount_item, price_final) FROM stdin;
1	1	1	1	1180.00	0	1180.00
2	1	2	1	1420.00	0	1420.00
3	1	4	1	1850.00	0	1850.00
27	13	2	1	1420.00	0	1420.00
29	13	5	1	2950.00	0	2950.00
4	2	1	4	1180.00	0	1180.00
6	2	3	2	980.00	0	980.00
30	13	4	1	1850.00	0	1850.00
17	9	2	3	1420.00	2	1391.60
5	2	2	5	1420.00	0	1420.00
9	3	3	1	980.00	0	980.00
7	3	1	2	1180.00	0	1180.00
8	3	2	2	1420.00	0	1420.00
10	5	2	1	1420.00	0	1420.00
11	5	4	1	1850.00	0	1850.00
12	5	1	1	1180.00	0	1180.00
13	5	1	1	1180.00	0	1180.00
14	5	3	1	980.00	0	980.00
31	13	3	1	980.00	0	980.00
16	9	2	1	1420.00	0	1420.00
20	10	2	1	1420.00	0	1420.00
21	10	3	1	980.00	0	980.00
18	9	4	2	1850.00	5	1757.50
35	14	4	5	1850.00	0	1850.00
19	10	1	5	1180.00	7	1097.40
23	11	2	1	1420.00	0	1420.00
24	11	3	1	980.00	0	980.00
22	11	1	100	1180.00	5	1121.00
34	14	3	30	980.00	0	980.00
32	14	1	10	1180.00	0	1180.00
33	14	2	19	1420.00	0	1420.00
36	14	5	1	2950.00	0	2950.00
37	15	1	1	1180.00	0	1180.00
38	15	2	1	1420.00	0	1420.00
15	9	1	14	1180.00	0	1180.00
39	16	1	13	1180.00	0	1180.00
40	16	2	10	1420.00	0	1420.00
26	12	2	1	1420.00	1	1405.80
25	12	1	10	1180.00	11	1050.20
\.


--
-- Data for Name: proposals; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.proposals (id, client_id, title, total_amount, discount_global, status, email_sent, created_at, updated_at, created_by, accepted_at) FROM stdin;
4	5	КП от 2026-06-01	0.00	20	draft	f	2026-06-02T02:55:28.978276	2026-06-02T02:55:28.978276	1	\N
6	5	КП от 2026-06-01	0.00	20	draft	f	2026-06-02T02:55:32.555945	2026-06-02T02:55:32.555945	1	\N
7	5	КП от 2026-06-01	0.00	20	draft	f	2026-06-02T02:55:32.634820	2026-06-02T02:55:32.634820	1	\N
8	5	КП от 2026-06-01	0.00	20	draft	f	2026-06-02T02:55:33.181567	2026-06-02T02:55:33.181567	1	\N
11	3	КП от 2026-06-02	101905.00	11	draft	f	2026-06-02T04:01:23.910828	2026-06-02T04:02:19.692805	1	\N
15	4	КП от 2026-06-02	2600.00	0	draft	f	2026-06-02T05:02:59.998384	2026-06-02T05:03:00.584192	1	\N
5	5	КП от 2026-06-01	5288.00	20	draft	f	2026-06-02T02:55:32.547159	2026-06-02T02:55:39.464120	1	\N
12	4	КП от 2026-06-02	10002.55	16	accepted	f	2026-06-02T04:15:33.818731	2026-06-02T04:21:29.092497	1	\N
9	5	КП от 2026-06-01	20503.84	20	draft	f	2026-06-02T02:55:54.169544	2026-06-02T02:57:47.307957	1	\N
13	3	КП от 2026-06-02	6840.00	5	draft	f	2026-06-02T04:21:44.175022	2026-06-02T04:21:50.606766	1	\N
10	6	КП от 2026-06-02	7887.00	0	accepted	f	2026-06-02T03:19:10.558846	2026-06-02T03:19:49.353312	1	\N
1	6	КП от 2026-05-29	4005.00	10	draft	f	2026-05-29T04:15:23.948160	2026-05-29T04:18:20.343096	\N	\N
16	6	КП от 2026-06-02	29540.00	0	accepted	f	2026-06-02T06:27:17.938900	2026-06-03T01:00:40.962930	1	2026-06-03T01:00:40.962930
2	4	КП от 2026-06-01	13780.00	0	accepted	f	2026-06-01T19:32:51.479080	2026-06-01T19:33:16.545385	1	\N
3	3	КП от 2026-06-01	5871.00	5	draft	f	2026-06-02T02:46:45.790205	2026-06-02T02:46:50.448736	1	\N
14	5	КП от 2026-06-02	80380.00	0	accepted	f	2026-06-02T04:26:57.745113	2026-06-02T04:29:35.379456	1	\N
\.


--
-- Data for Name: sku_catalog; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.sku_catalog (id, sku, category, gost, d_inner, d_outer, b_width, type, brand, stock, price, img, created_at) FROM stdin;
1	HHB UCP 206	housing	480206	30.00	62.00	38.10	Корпусной узел на лапах (Pillow Block)	HHB	Достаточно	1180.00	images/ucp.jpg	2026-05-28T22:56:59.427424
2	HHB UCF 208	housing	480208	40.00	80.00	49.20	Квадратный фланцевый узел (Flange Block)	HHB	Достаточно	1420.00	images/ucf.jpg	2026-05-28T22:56:59.427424
3	HHB UCFL 205	housing	480205	25.00	52.00	34.10	Ромбический фланцевый узел (2-bolt Flange)	HHB	Достаточно	980.00	images/ucfl.jpg	2026-05-28T22:56:59.427424
4	HHB UCT 207	housing	480207	35.00	72.00	42.90	Натяжной узел для нории (Take-up Unit)	HHB	В наличии	1850.00	images/uct.jpg	2026-05-28T22:56:59.427424
5	HHB STAINLESS UC 204	stainless	SS480204	20.00	47.00	31.00	Нержавеющая сталь (Stainless Series)	HHB	18 шт	2950.00	images/stainless.jpg	2026-05-28T22:56:59.427424
6	FKD UK 208 + H2308	housing	UK208	35.00	80.00	49.00	С конической закрепительной втулкой	FKD	95 шт	1620.00	images/uk.jpg	2026-05-28T22:56:59.427424
7	FKD NA 206	housing	NA206	30.00	62.00	36.40	С эксцентриковым стопорным кольцом	FKD	Достаточно	730.00	images/na.jpg	2026-05-28T22:56:59.427424
8	HHB 22315-E1-T41A	roller	3615	75.00	160.00	55.00	Сферический роликовый для виброгрохотов	HHB	12 шт	7950.00	images/spherical.jpg	2026-05-28T22:56:59.427424
9	HHB 6205-2RS C3	ball	180205	25.00	52.00	15.00	Радиальный шариковый с увеличенным зазором	HHB	1 240 шт	420.00	frames_eevee/mobile_webp/0060.webp	2026-05-28T22:56:59.427424
10	HHB 6206-2RS C3	ball	180206	30.00	62.00	16.00	Радиальный шариковый с зазором C3	HHB	850 шт	540.00	frames_eevee/mobile_webp/0060.webp	2026-05-28T22:56:59.427424
11	FKD UC 210	housing	480210	50.00	90.00	51.60	Шариковый радиальный под закрепительный винт	FKD	320 шт	690.00	images/ucp.jpg	2026-05-28T22:56:59.427424
12	Сальник 30х52х10 (Манжета)	cuffs	8752-79	30.00	52.00	10.00	Армированная одновальная манжета ГОСТ	FKD	Достаточно	180.00	frames_eevee/mobile_webp/0060.webp	2026-05-28T22:56:59.427424
13	HHB NU 312 ECP	roller	12312	60.00	130.00	31.00	Цилиндрический роликовый	HHB	45 шт	4300.00	images/roller.jpg	2026-05-28T22:56:59.427424
14	HHB 6308-2RS	ball	180308	40.00	90.00	23.00	Радиальный шариковый однорядный	HHB	560 шт	890.00	images/ball.jpg	2026-05-28T22:56:59.427424
15	FKD UCP 209	housing	480209	45.00	85.00	49.20	Корпусной узел на лапах	FKD	120 шт	1050.00	images/ucp.jpg	2026-05-28T22:56:59.427424
16	DECOMP-SKU-POST-1	housing		\N	\N	\N				0.00		2026-06-01T22:17:57.115285
\.


--
-- Data for Name: tasks; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.tasks (id, assigned_to, created_by, lead_id, call_id, title, description, priority, due_date, status, source, created_at, completed_at, updated_at, estimated_minutes) FROM stdin;
6	6	ai_agent	\N	\N	Перезвонить ООО Ромашка по КП	\N	high	2026-06-01T06:04:45.810613	done	manual	2026-06-01T02:04:45.810660	\N	2026-06-02T04:23:09.754024	\N
1	6	ai_agent	\N	\N	Позвонить в агрохолдинг	Обзвон агрохолдинга — выявить потребность в подшипниках для сельхозтехники/элеваторов	normal	2026-06-01T20:37:39.973567	done	manual	2026-05-31T20:37:39.973597	\N	2026-06-02T06:24:55.757337	\N
24	6	admin	\N	\N	Позвонить за подтверждением в мираторг		medium	2026-06-02T05:30:20.914443	done	manual	2026-06-02T04:30:20.914458	\N	2026-06-02T06:26:12.116219	60
\.


--
-- Data for Name: users; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.users (id, username, password_hash, name, role, created_at) FROM stdin;
1	admin	5ce9b7b8fae2066cbb1b459cd9926f64$bf40cb27c71428ffcff42330c2db7d6494f9bcc82fb214f7498ba00f7ef9c9b3	Администратор	admin	2026-05-28T22:56:59.436695
5	Kris	41595fe78097826da75068d656b24b63$722cbb033aa69035d8ff67ba0d7c4d60919775f78b359751e8b45ec79a67bee7	Кристина Черных	manager	2026-05-28T23:17:52.346008
6	ivan	d3f3333d4cc267ebc2d3dbffe8fa8a33$6186349a261bdb237ebd6f5e10ff86b7adc97a633ba0b9f4afc26b6bb2d48b3b	Иван	employee	2026-05-28T23:55:34.741825
7	Dima	015157d066e4ad7b0a50b8555fa52a96$b71c60e2f05554f3a27110bd42b89d2065e532cc1bea08bcd0f2221fd9277899	Дмитрий	employee	2026-06-02T06:08:47.420639
8	Andrei	7d0831e1e02d8034cadb099d092eb6fb$cb705d4c0d9eef4567a2133386cad975ab2f7a06f01b062345d56a421e3fe614	андрей	manager	2026-06-02T06:14:22.958353
\.


--
-- Name: calendar_events_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.calendar_events_id_seq', 1, false);


--
-- Name: call_logs_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.call_logs_id_seq', 1, false);


--
-- Name: clients_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.clients_id_seq', 7, true);


--
-- Name: daily_plans_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.daily_plans_id_seq', 17, true);


--
-- Name: employee_plans_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.employee_plans_id_seq', 1, true);


--
-- Name: notes_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.notes_id_seq', 6, true);


--
-- Name: parsed_leads_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.parsed_leads_id_seq', 11, true);


--
-- Name: proposal_items_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.proposal_items_id_seq', 40, true);


--
-- Name: proposals_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.proposals_id_seq', 16, true);


--
-- Name: sku_catalog_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.sku_catalog_id_seq', 16, true);


--
-- Name: tasks_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.tasks_id_seq', 16, true);


--
-- Name: tasks_id_seq1; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.tasks_id_seq1', 31, true);


--
-- Name: users_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.users_id_seq', 8, true);


--
-- Name: calendar_events calendar_events_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.calendar_events
    ADD CONSTRAINT calendar_events_pkey PRIMARY KEY (id);


--
-- Name: call_logs call_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.call_logs
    ADD CONSTRAINT call_logs_pkey PRIMARY KEY (id);


--
-- Name: clients clients_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.clients
    ADD CONSTRAINT clients_pkey PRIMARY KEY (id);


--
-- Name: daily_plans daily_plans_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.daily_plans
    ADD CONSTRAINT daily_plans_pkey PRIMARY KEY (id);


--
-- Name: daily_plans daily_plans_user_id_date_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.daily_plans
    ADD CONSTRAINT daily_plans_user_id_date_key UNIQUE (user_id, date);


--
-- Name: employee_plans employee_plans_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.employee_plans
    ADD CONSTRAINT employee_plans_pkey PRIMARY KEY (id);


--
-- Name: employee_plans employee_plans_user_id_month_year_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.employee_plans
    ADD CONSTRAINT employee_plans_user_id_month_year_key UNIQUE (user_id, month, year);


--
-- Name: notes notes_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.notes
    ADD CONSTRAINT notes_pkey PRIMARY KEY (id);


--
-- Name: parsed_leads parsed_leads_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.parsed_leads
    ADD CONSTRAINT parsed_leads_pkey PRIMARY KEY (id);


--
-- Name: proposal_items proposal_items_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.proposal_items
    ADD CONSTRAINT proposal_items_pkey PRIMARY KEY (id);


--
-- Name: proposals proposals_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.proposals
    ADD CONSTRAINT proposals_pkey PRIMARY KEY (id);


--
-- Name: sku_catalog sku_catalog_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.sku_catalog
    ADD CONSTRAINT sku_catalog_pkey PRIMARY KEY (id);


--
-- Name: sku_catalog sku_catalog_sku_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.sku_catalog
    ADD CONSTRAINT sku_catalog_sku_key UNIQUE (sku);


--
-- Name: job_queue tasks_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.job_queue
    ADD CONSTRAINT tasks_pkey PRIMARY KEY (id);


--
-- Name: tasks tasks_pkey1; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.tasks
    ADD CONSTRAINT tasks_pkey1 PRIMARY KEY (id);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: users users_username_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_username_key UNIQUE (username);


--
-- Name: calendar_events calendar_events_client_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.calendar_events
    ADD CONSTRAINT calendar_events_client_id_fkey FOREIGN KEY (client_id) REFERENCES public.clients(id) ON DELETE SET NULL;


--
-- Name: call_logs call_logs_client_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.call_logs
    ADD CONSTRAINT call_logs_client_id_fkey FOREIGN KEY (client_id) REFERENCES public.clients(id) ON DELETE SET NULL;


--
-- Name: call_logs call_logs_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.call_logs
    ADD CONSTRAINT call_logs_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: daily_plans daily_plans_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.daily_plans
    ADD CONSTRAINT daily_plans_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: employee_plans employee_plans_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.employee_plans
    ADD CONSTRAINT employee_plans_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: notes notes_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.notes
    ADD CONSTRAINT notes_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: parsed_leads parsed_leads_assigned_to_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.parsed_leads
    ADD CONSTRAINT parsed_leads_assigned_to_fkey FOREIGN KEY (assigned_to) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: proposal_items proposal_items_proposal_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.proposal_items
    ADD CONSTRAINT proposal_items_proposal_id_fkey FOREIGN KEY (proposal_id) REFERENCES public.proposals(id) ON DELETE CASCADE;


--
-- Name: proposal_items proposal_items_sku_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.proposal_items
    ADD CONSTRAINT proposal_items_sku_id_fkey FOREIGN KEY (sku_id) REFERENCES public.sku_catalog(id) ON DELETE CASCADE;


--
-- Name: proposals proposals_client_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.proposals
    ADD CONSTRAINT proposals_client_id_fkey FOREIGN KEY (client_id) REFERENCES public.clients(id) ON DELETE SET NULL;


--
-- Name: tasks tasks_assigned_to_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.tasks
    ADD CONSTRAINT tasks_assigned_to_fkey FOREIGN KEY (assigned_to) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: tasks tasks_call_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.tasks
    ADD CONSTRAINT tasks_call_id_fkey FOREIGN KEY (call_id) REFERENCES public.call_logs(id) ON DELETE SET NULL;


--
-- Name: tasks tasks_lead_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.tasks
    ADD CONSTRAINT tasks_lead_id_fkey FOREIGN KEY (lead_id) REFERENCES public.parsed_leads(id) ON DELETE SET NULL;


--
-- PostgreSQL database dump complete
--

\unrestrict iz9oIflLZWclnEG5ItRg9yjWJdzBe2qefZFJdJmK1YcJUHegaJLCYHhFBl5onnQ

