// Repair numbers match the PC window: META=0, source index+1=DATA.
export function repairSummary(receiver) {
  if (!receiver?.meta) return {
    numbers: "0", count: null,
    message: "文件信息帧尚未收到：请在 PC 输入 0，点击“仅补发列表”。收到前无法确定总分片数，数据帧暂不保留；收到后再计算数据缺片。",
  };
  const missing = receiver.missingSources(receiver.meta.sourceCount).map((index) => index + 1);
  const ranges = [];
  for (let i = 0; i < missing.length; i += 1) {
    const first = missing[i];
    let last = first;
    while (i + 1 < missing.length && missing[i + 1] === last + 1) last = missing[++i];
    ranges.push(first === last ? String(first) : `${first}-${last}`);
  }
  return {
    numbers: ranges.join(","), count: missing.length,
    message: missing.length ? `文件信息帧 0 已收到；尚缺 ${missing.length} 个原始数据分片。将下方编号输入 PC，点击“仅补发列表”。也可输入其中一个编号，点击“从编号播放”。`
      : "文件信息帧及所有原始数据均已收到，无需补发。",
  };
}
