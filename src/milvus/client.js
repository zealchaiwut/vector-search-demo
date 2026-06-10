let _client = null;

class MilvusClientWrapper {
  constructor() {
    this._sdk = null;
    this._address = null;
  }

  _getAddress() {
    const host = process.env.MILVUS_HOST || "localhost";
    const port = process.env.MILVUS_PORT || "19530";
    return `${host}:${port}`;
  }

  async _init() {
    if (this._sdk) return;
    const { MilvusClient } = await import("@zilliz/milvus2-sdk-node");
    this._address = this._getAddress();
    this._sdk = new MilvusClient({ address: this._address });
  }

  async ping() {
    await this._init();
    const res = await this._sdk.getVersion();
    return res.version || res.Version || String(res);
  }

  getAddress() {
    return this._address || this._getAddress();
  }
}

export function getMilvusClient() {
  if (!_client) {
    _client = new MilvusClientWrapper();
  }
  return _client;
}
