-- LuftBase 0.1.0a109 - tb_sistema: integracao com o LuftBase, tipo de acesso e URL de download.
--
-- Equivale a migracao Alembic 20261015_0016 e pode ser executada em homologacao e em producao, com
-- um usuario dono das tabelas do schema core (ex.: o administrativo de migracao).
--
--   * Aditivo: so acrescenta colunas com valor padrao (sistemas atuais ficam integrados e WEB).
--   * Repetivel: ADD COLUMN IF NOT EXISTS e constraints protegidas; rodar duas vezes nao faz mal.
--   * Em uma transacao: se algo falhar, nada e aplicado.
--   * Carimba a revisao do Alembic em 20261015_0016 SO se o core estiver na 20261008_0015, para o
--     `banco atualizar` do Workspace nao tentar aplicar de novo. Em outra revisao nao mexe nela; a
--     migracao e idempotente e termina o trabalho depois.
--
-- Confira o resultado nas duas consultas do fim.

BEGIN;

ALTER TABLE core.tb_sistema ADD COLUMN IF NOT EXISTS integra_luftbase boolean NOT NULL DEFAULT true;
ALTER TABLE core.tb_sistema ADD COLUMN IF NOT EXISTS tipo_acesso varchar(20) NOT NULL DEFAULT 'WEB';
ALTER TABLE core.tb_sistema ADD COLUMN IF NOT EXISTS url_download varchar(500);

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'ck_core_sistema_tipo_acesso' AND conrelid = 'core.tb_sistema'::regclass
    ) THEN
        ALTER TABLE core.tb_sistema ADD CONSTRAINT ck_core_sistema_tipo_acesso
            CHECK (tipo_acesso IN ('WEB', 'DOWNLOAD', 'SEM_ACESSO'));
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'ck_core_sistema_url_download' AND conrelid = 'core.tb_sistema'::regclass
    ) THEN
        ALTER TABLE core.tb_sistema ADD CONSTRAINT ck_core_sistema_url_download
            CHECK ((tipo_acesso <> 'DOWNLOAD' OR url_download IS NOT NULL)
                   AND (integra_luftbase = false OR tipo_acesso = 'WEB'));
    END IF;
END $$;

UPDATE core.alembic_version SET version_num = '20261015_0016' WHERE version_num = '20261008_0015';

COMMIT;

-- Conferencia
SELECT version_num AS revisao_do_core FROM core.alembic_version;
SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_schema = 'core' AND table_name = 'tb_sistema'
  AND column_name IN ('integra_luftbase', 'tipo_acesso', 'url_download')
ORDER BY column_name;
