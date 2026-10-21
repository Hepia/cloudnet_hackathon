// Runs once, when the mongo container initialises its empty data directory
// (database "open5gs", see MONGO_INITDB_DATABASE in docker-compose.yml).
// Same document as `open5gs-dbctl add <imsi> <k> <opc>`. UERANSIM's ue.yaml uses the first IMSI;
// `UE_COUNT=n` starts n UEs with consecutive IMSIs, so a few are provisioned.
const K = "00112233445566778899aabbccddeeff";
const OPC = "63BFA50EE6523365FF14C1F45F88737D";
const imsis = ["001010123456780", "001010123456781", "001010123456782", "001010123456783", "001010123456784"];

for (const imsi of imsis) {
  db.subscribers.insertOne({
    _id: new ObjectId(),
    schema_version: NumberInt(1),
    imsi: imsi,
    msisdn: [],
    imeisv: [],
    mme_host: [],
    mm_realm: [],
    purge_flag: [],
    slice: [{
      sst: NumberInt(1),
      default_indicator: true,
      session: [{
        name: "internet",
        type: NumberInt(1),                       // IPv4
        qos: { index: NumberInt(9), arp: { priority_level: NumberInt(8), pre_emption_capability: NumberInt(1), pre_emption_vulnerability: NumberInt(2) } },
        ambr: { downlink: { value: NumberInt(1000000000), unit: NumberInt(0) }, uplink: { value: NumberInt(1000000000), unit: NumberInt(0) } },
        pcc_rule: [],
        _id: new ObjectId(),
      }],
      _id: new ObjectId(),
    }],
    security: { k: K, op: null, opc: OPC, amf: "8000" },
    ambr: { downlink: { value: NumberInt(1000000000), unit: NumberInt(0) }, uplink: { value: NumberInt(1000000000), unit: NumberInt(0) } },
    access_restriction_data: 32,
    network_access_mode: 0,
    subscriber_status: 0,
    operator_determined_barring: 0,
    subscribed_rau_tau_timer: 12,
    __v: 0,
  });
}
print("subscribers: " + db.subscribers.countDocuments({}));
