# Mismo motor que la base (postgres:17): pg_basebackup y pg_combinebackup deben coincidir.
FROM postgres:17
RUN mkdir -p /backups /restore && chown postgres:postgres /backups /restore
COPY --chmod=755 respaldo.sh restaurar.sh programador.sh /usr/local/bin/
USER postgres
ENTRYPOINT []
CMD ["programador.sh"]
