-- Schema PostgreSQL / Supabase para controle de trials, licenças por máquina e pedidos Pix do XMDL
create extension if not exists pgcrypto;

create table if not exists public.clientes (
    id uuid primary key default gen_random_uuid(),
    nome text not null,
    cpf_cnpj varchar(20) not null unique,
    email text not null,
    telefone varchar(40) not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists public.trials (
    id uuid primary key default gen_random_uuid(),
    cliente_id uuid not null references public.clientes(id) on delete cascade,
    machine_id varchar(128) not null,
    machine_name text,
    install_id varchar(64),
    app_version varchar(40),
    started_at timestamptz not null default now(),
    expires_at timestamptz not null,
    status varchar(20) not null default 'active',
    last_sync_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);
create unique index if not exists uq_trials_cliente on public.trials(cliente_id);

create table if not exists public.licencas (
    id uuid primary key default gen_random_uuid(),
    cliente_id uuid not null references public.clientes(id) on delete cascade,
    total_comprado integer not null default 0,
    total_em_uso integer not null default 0,
    status varchar(20) not null default 'inactive',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);
create unique index if not exists uq_licencas_cliente on public.licencas(cliente_id);

create table if not exists public.pedidos (
    id uuid primary key default gen_random_uuid(),
    cliente_id uuid not null references public.clientes(id) on delete cascade,
    quantidade integer not null check (quantidade > 0),
    total_amount numeric(12,2) not null,
    status varchar(20) not null default 'pending',
    pix_copy_paste text,
    pix_qr_code text,
    external_reference text,
    mercadopago_payment_id text,
    mercadopago_status text,
    mercadopago_status_detail text,
    mercadopago_payload jsonb,
    webhook_last_received_at timestamptz,
    expires_at timestamptz,
    paid_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);
create index if not exists idx_pedidos_cliente_status on public.pedidos(cliente_id, status);
create index if not exists idx_pedidos_mp_payment on public.pedidos(mercadopago_payment_id);

create table if not exists public.ativacoes (
    id uuid primary key default gen_random_uuid(),
    licenca_id uuid not null references public.licencas(id) on delete cascade,
    cliente_id uuid not null references public.clientes(id) on delete cascade,
    machine_id varchar(128) not null,
    machine_name text,
    install_id varchar(64),
    app_version varchar(40),
    status varchar(20) not null default 'active',
    activated_at timestamptz,
    last_ping_at timestamptz,
    deactivated_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);
create unique index if not exists uq_ativacoes_licenca_machine on public.ativacoes(licenca_id, machine_id);
create index if not exists idx_ativacoes_cliente_status on public.ativacoes(cliente_id, status);

create or replace function public.touch_updated_at()
returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

create or replace function public.fn_marcar_pedido_como_pago(
    p_order_id uuid,
    p_payment_id text default null,
    p_status_detail text default null
)
returns void as $$
declare
  v_cliente_id uuid;
begin
  update public.pedidos
     set status = 'paid',
         mercadopago_payment_id = coalesce(p_payment_id, mercadopago_payment_id),
         mercadopago_status = 'approved',
         mercadopago_status_detail = coalesce(p_status_detail, mercadopago_status_detail),
         paid_at = coalesce(paid_at, now()),
         updated_at = now()
   where id = p_order_id
   returning cliente_id into v_cliente_id;

  if v_cliente_id is null then
    raise exception 'Pedido % não encontrado', p_order_id;
  end if;

  update public.licencas
     set total_comprado = (
           select coalesce(sum(quantidade), 0)
             from public.pedidos
            where cliente_id = v_cliente_id
              and status = 'paid'
         ),
         status = case
           when (
             select coalesce(sum(quantidade), 0)
               from public.pedidos
              where cliente_id = v_cliente_id
                and status = 'paid'
           ) > 0 then 'active' else 'inactive' end,
         updated_at = now()
   where cliente_id = v_cliente_id;
end;
$$ language plpgsql;

drop trigger if exists trg_clientes_touch_updated_at on public.clientes;
create trigger trg_clientes_touch_updated_at before update on public.clientes
for each row execute function public.touch_updated_at();

drop trigger if exists trg_trials_touch_updated_at on public.trials;
create trigger trg_trials_touch_updated_at before update on public.trials
for each row execute function public.touch_updated_at();

drop trigger if exists trg_licencas_touch_updated_at on public.licencas;
create trigger trg_licencas_touch_updated_at before update on public.licencas
for each row execute function public.touch_updated_at();

drop trigger if exists trg_pedidos_touch_updated_at on public.pedidos;
create trigger trg_pedidos_touch_updated_at before update on public.pedidos
for each row execute function public.touch_updated_at();

drop trigger if exists trg_ativacoes_touch_updated_at on public.ativacoes;
create trigger trg_ativacoes_touch_updated_at before update on public.ativacoes
for each row execute function public.touch_updated_at();
