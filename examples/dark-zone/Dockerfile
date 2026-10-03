# The dark-zone demo service: the DCP SDK and the OpenLineage bridge, installed
# from this repository, plus the demo's plain scripts. Build context: the repo root.
FROM python:3.12-slim

WORKDIR /demo
COPY sdk-python /src/sdk-python
COPY bridges/openlineage /src/bridges/openlineage
RUN pip install --no-cache-dir "/src/sdk-python[postgres,kafka]" /src/bridges/openlineage

COPY examples/dark-zone/run-demo.sh examples/dark-zone/wait_for.py examples/dark-zone/seed.py \
     examples/dark-zone/nightly_enrich.py examples/dark-zone/warehouse_loader.py /demo/
# Second line of defence for a Windows checkout made before .gitattributes
# existed: strip CRs, so bash and the shebang line work.
RUN sed -i 's/\r$//' /demo/*.sh /demo/*.py && chmod +x /demo/run-demo.sh

ENTRYPOINT ["/demo/run-demo.sh"]
