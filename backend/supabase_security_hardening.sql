-- Endurecimento básico para os avisos do Security Advisor no Supabase.
-- Uso sugerido para este projeto: API acessando com service_role no backend,
-- sem expor diretamente estas tabelas para anon/authenticated.

begin;

-- 1) Habilitar RLS nas tabelas expostas do schema public.
alter table if exists public.clientes enable row level security;
alter table if exists public.trials enable row level security;
alter table if exists public.pedidos enable row level security;
alter table if exists public.licencas enable row level security;
alter table if exists public.ativacoes enable row level security;

-- 2) Como este backend usa service_role, o mais seguro é não liberar acesso direto
-- para anon/authenticated nestas tabelas.
revoke all on table public.clientes from anon, authenticated;
revoke all on table public.trials from anon, authenticated;
revoke all on table public.pedidos from anon, authenticated;
revoke all on table public.licencas from anon, authenticated;
revoke all on table public.ativacoes from anon, authenticated;

-- Mantém uso pleno para o papel de serviço.
grant all on table public.clientes to service_role;
grant all on table public.trials to service_role;
grant all on table public.pedidos to service_role;
grant all on table public.licencas to service_role;
grant all on table public.ativacoes to service_role;

-- 3) Ajustar a view sinalizada pelo advisor para obedecer permissões do chamador.
-- Se a view não existir, esta linha pode ser comentada.
alter view if exists public.vw_resumo_licenciamento
set (security_invoker = true);

commit;
