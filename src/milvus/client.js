let _client = null;

class MilvusClientWrapper {
  constructor() {
    this._sdk = null;
    this._address = null;
  }

  _getAddress() {
    // MILVUS_HOST/MILVUS_PORT take precedence (used by live tests);
    // otherwise honor MILVUS_ADDRESS from .env (see .env.example).
    const host = process.env.MILVUS_HOST;
    const port = process.env.MILVUS_PORT;
    if (host || port) {
      return `${host || "localhost"}:${port || "19530"}`;
    }
    return process.env.MILVUS_ADDRESS || "localhost:19530";
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
