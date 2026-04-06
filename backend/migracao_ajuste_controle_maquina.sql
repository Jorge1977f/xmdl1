-- Ajustes para endurecer o controle por máquina e habilitar Mercado Pago real.
-- Execute no Supabase SQL Editor no banco atual antes de publicar a versão de produção.

alter table public.trials add column if not exists install_id varchar(64);

alter table public.ativacoes add column if not exists install_id varchar(64);

alter table public.pedidos add column if not exists external_reference text;
alter table public.pedidos add column if not exists mercadopago_status text;
alter table public.pedidos add column if not exists mercadopago_status_detail text;
alter table public.pedidos add column if not exists mercadopago_payload jsonb;
alter table public.pedidos add column if not exists webhook_last_received_at timestamptz;

create unique index if not exists uq_trials_cliente on public.trials(cliente_id);
create unique index if not exists uq_licencas_cliente on public.licencas(cliente_id);
create unique index if not exists uq_ativacoes_licenca_machine on public.ativacoes(licenca_id, machine_id);
create index if not exists idx_pedidos_cliente_status on public.pedidos(cliente_id, status);
create index if not exists idx_ativacoes_cliente_status on public.ativacoes(cliente_id, status);
create index if not exists idx_pedidos_mp_payment on public.pedidos(mercadopago_payment_id);

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
