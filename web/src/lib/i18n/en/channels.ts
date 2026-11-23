// Testi inglesi: area «channels» (WP4, condivisione dei canali). Il tipo obbliga a tradurre ogni chiave italiana.
import type { channels as itArea } from '../it/channels'

export const channels: Record<keyof typeof itArea, string> = {
  'channels.failed': "Channel link not available",
  'channels.bits256': "256-bit",
  'channels.bits128': "128-bit",
  'channels.bitsLabel': "Length of the generated key",
  'channels.weak.default': "Default public key (AQ==): anyone with the same app reads this channel",
  'channels.weak.none': "No encryption: messages on this channel travel in clear text",
  'channels.weak.body': "For a private channel generate a new key and share it only with those who should join.",
  'channels.share.open': "Share channels",
  'channels.share.needRead': "Read the node configuration again to share its channels",
  'channels.share.title': "Share the channels",
  'channels.share.localOnly': "The link contains the channel keys: it is shown only on the PC running MeshLens",
  'channels.share.warning': "Anyone with this QR code or link joins the channels and reads their messages",
  'channels.share.mode': "Link type",
  'channels.share.replace': "Replace channels",
  'channels.share.add': "Add channels",
  'channels.share.channel': "Channel {n}: {name}",
  'channels.share.primaryRequired': "To replace the channels the primary channel (0) is also needed",
  'channels.share.update': "Update the QR code",
  'channels.share.qrAria': "Channel QR code",
  'channels.share.copy': "Copy the link",
  'channels.share.copied': "Link copied",
}
