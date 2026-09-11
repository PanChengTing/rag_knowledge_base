ARG PG_MAJOR=16

FROM postgres:${PG_MAJOR}-bookworm AS builder

ARG PG_MAJOR
RUN apt-get update\
    && apt-get install -y --no-install-recommends\
    build-essential\
    ca-certificates\
    curl\
    git\
    postgresql-server-dev-${PG_MAJOR}\
    && rm -rf /var/lib/apt/lists/*
RUN curl -fsSL http://www.xunsearch.com/scws/down/scws-1.2.3.tar.bz2 -o /tmp/scws.tar.bz2 \
    && mkdir -p /tmp/scws \
    && tar -xjf /tmp/scws.tar.bz2 -C /tmp/scws --strip-components=1 \
    && cd /tmp/scws\
    && ./configure \
    && make -j"$(nproc)" \
    && make install
RUN git clone --depth 1 https://github.com/amutu/zhparser.git /tmp/zhparser \
    && cd /tmp/zhparser \
    && make \
    && make install

FROM pgvector/pgvector:pg16
ARG PG_MAJOR=16

COPY --from=builder /usr/lib/postgresql/${PG_MAJOR}/lib/zhparser.so \
    /usr/lib/postgresql/${PG_MAJOR}/lib/
COPY --from=builder /usr/share/postgresql/${PG_MAJOR}/extension/zhparser* \
    /usr/share/postgresql/${PG_MAJOR}/extension/
COPY --from=builder /usr/local/lib/libscws.* \
/usr/local/lib/
COPY --from=builder /usr/share/postgresql/${PG_MAJOR}/tsearch_data/ \
/usr/share/postgresql/${PG_MAJOR}/tsearch_data/

RUN ldconfig