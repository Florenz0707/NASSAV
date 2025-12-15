FROM golang:1.22-alpine AS m3u8-builder

WORKDIR /build

RUN apk add --no-cache git

RUN git clone https://github.com/Greyh4t/m3u8-Downloader-Go.git src && \
    cd src && git checkout tags/v1.5.2 && \
    go build -o /build/m3u8-Downloader-Go

FROM alpine:latest AS nassav

WORKDIR /NASSAV

RUN apk add --no-cache ffmpeg python3 && \
    rm -rf /var/cache/apk/*

COPY . .

COPY --from=m3u8-builder /build/m3u8-Downloader-Go tools/m3u8-Downloader-Go

RUN python -m venv .

RUN ./bin/pip install --no-cache-dir -r requirements.txt

ENTRYPOINT ["./bin/python", "main.py"]
