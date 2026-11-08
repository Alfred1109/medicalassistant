const expectedSet = "rehab_rs";
try {
  const config = rs.conf();
  if (config._id !== expectedSet || config.members.length !== 1 ||
      config.members[0].host !== "127.0.0.1:27017") {
    throw new Error("Existing replica configuration differs; refusing to reconfigure it");
  }
} catch (error) {
  if (error.code !== 94) throw error; // NotYetInitialized only
  const result = rs.initiate({
    _id: expectedSet,
    members: [{_id: 0, host: "127.0.0.1:27017"}],
  });
  if (result.ok !== 1) throw new Error(JSON.stringify(result));
}
