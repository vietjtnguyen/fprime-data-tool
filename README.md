# F Prime Data Tool

F Prime Data Tool (`fprime-data-tool`) is a command line utility that can be used to read F Prime data in binary form. This includes the output of `ComLogger` objects and the binary `recv.bin` logs generated by `fprime-gds`.  It includes different output options that are conducive to data analysis.

## Input Formats

### Concatenated Records

The "concatenated records" input format is basically records written one after another.  A record can be any type (see the `--record-type` option), but it is typically a struct containing the length (stored by some unsigned integer) of a F Prime packet (basically an `Fw::ComPacket`) followed by the F Prime packet itself.  Below is C code defining this structure, specifically `ComLoggerRecord`, along with telemetry and event packet details.with a note that it is packed when serialized (no padding).

```c
struct __attribute__((__packed__)) ComLoggerRecord {
    uint16_t packet_size;
    struct __attribute__((__packed__)) {
        FwPacketDescriptorType /*uint32_t*/ type;
        union {

            // packet_type == 1 (TELEM)
            struct __attribute__((__packed__)) {
                FwChanIdType /*uint32_t*/ channel_id;
                struct __attribute__((__packed__)) {
                    FwTimeBaseStoreType /*uint16_t*/ base;
                    FwTimeContextStoreType /*uint8_t*/ context;
                    uint32_t seconds;
                    uint32_t microseconds;
                } time;
                char* value;
            } telem;

            // packet_type == 2 (LOG)
            struct __attribute__((__packed__)) {
                FwEventIdType /*uint32_t*/ event_id;
                struct __attribute__((__packed__)) {
                    FwTimeBaseStoreType /*uint16_t*/ base;
                    FwTimeContextStoreType /*uint8_t*/ context;
                    uint32_t seconds;
                    uint32_t microseconds;
                } time;
                char* arguments;
            } event;

      } payload;
    } packet;
} record;
```

The packet size stored in the record header is equal to the size of the underlying F Prime packet.  For example, an event packet with no arguments is 19 bytes (`uint32_t` + `uint32_t` + `uint16_t` + `uint8_t` + `uint32_t` + `uint32_t`).  The packet size written will be 19.

This format covers two different logs: the `recv.bin` log generated by [`fprime-gds`](https://github.com/fprime-community/fprime-gds) and the `*.com` logs generated by [`ComLogger`](https://github.com/nasa/fprime/tree/devel/Svc/ComLogger).  The `fprime-gds` log uses `uint32_t` to store the packet size while `ComLogger` uses a `uint16_t`.

Set `--record-type` to `ComLoggerRecord` to read `ComLogger` logs.

Set `--record-type` to `FprimeGdsRecord` to read `fprime-gds` `recv.bin` logs.

Set `--record-type` to `PrmDbRecord` to read [`PrmDb.dat` files](https://github.com/nasa/fprime/tree/devel/Svc/PrmDb).

## Output Formats

### vnlog

This is the default output format which is a whitespace delimited tabular format conducive to quick analysis using [vnlog](https://github.com/dkogan/vnlog) tools such as `vnl-filter` and [feedgnuplot](https://github.com/dkogan/feedgnuplot).

For example you can plot a crude timeline of all events:

```sh
fprime-data-tool \
    -d fsw-dictionary.xml \
    --record-type FprimeGdsRecord \
    recv.bin \
| vnl-filter \
    -p 'event_time,event_topology_name,event_id' \
    'event_component!="-"' \
| feedgnuplot --domain --dataid --autolegend
```

### Tab separated values (TSV)

This is particularly useful for being ingested into [visidata](https://www.visidata.org/).  In fact, the tool will not support a CSV output format directly because you can just use visidata to do the conversion:

```sh
fprime-data-tool \
    -F tsv \
    -d fsw-dictionary.xml \
    --record-type FprimeGdsRecord \
    recv.bin \
| visidata - -b -o recv.csv
```

### JSON

For complex payloads where values and arguments are composed of custom arrays or custom serializables the tabular formats cannot capture the complexity easily.  The JSON format, however, can and is very useful for deep inspection of the data, especially when paired with tools like [`jq`](https://jqlang.github.io/jq/).

## Cookbook

### Print JSON object of time and value for all telemetry for component `navigation` and channel `PosePosition`

```sh
fprime-data-tool \
    -F json \
    -d fsw-dictionary.xml \
    --record-type FprimeGdsRecord \
    gds-log2/recv.bin \
| jq 'select(.packet.payload.topology_name == "navigation.PosePosition") | {"time": .packet.payload.time.value, "value": .packet.payload.value}' -c
```

### Count number of times a particular event occurs in a `ComLogger` log

```sh
fprime-data-tool \
    -d fsw-dictionary.xml \
    --record-type ComLoggerRecord \
    myComLoggerLog.com \
| vnl-filter 'event_topology_name=="imu.SaturationError"' \
| wc -l
```

### See all `WARNING_HI` events in a `fprime-gds` `recv.bin` log

```sh
fprime-data-tool \
    -d fsw-dictionary.xml \
    --record-type FprimeGdsRecord \
    recv.bin \
| vnl-filter -p 'event' 'event_severity=="WARNING_HI"' \
| vnl-align \
| less -S
```

### Create CSV of all records in a `fprime-gds` `recv.bin` log

```sh
fprime-data-tool \
    -F tsv \
    -d fsw-dictionary.xml \
    --record-type FprimeGdsRecord \
    recv.bin \
| visidata - -b -o recv.csv
```

### Use `jq` to get ISO 8601 timestamp of all `fpga` component telemetry packets in a `ComLogger` log

```sh
fprime-data-tool \
    -d fsw-dictionary.xml \
    --record-type ComLoggerRecord \
    -F json \
    myComLoggerLog.com \
| jq 'select(.packet.type == "TELEM") | select(.packet.payload.component == "fpga") | .packet.payload.time.utc_iso8601'
```

### Print parameters for `globalPlanner` component in a `PrmDb.dat` file as JSON

```sh
fprime-data-tool \
    -d fsw-dictionary.xml \
    --record-type PrmDbRecord \
    -F json \
    PrmDb.dat \
| jq 'select(.component == "globalPlanner")'
```

## Future Work

- Add Python packaging (i.e. `setup.py`)
- Support encoding of command packets
- Support validating commands
- Support encoding of file packets given a file
- Support encoding of telemetry packets
- Support encoding of event packets
- Support encoding into `fprime-gds` protocol (with `0xDEADBEEF` sync marker)
- Add [Textual](https://textual.textualize.io/) terminal user interface (TUI) front end
- Support generating sequence files
- Support writing parameter files
