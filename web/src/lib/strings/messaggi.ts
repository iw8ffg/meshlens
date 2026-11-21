/** Testi della schermata Messaggi: ogni frase e' intera, pronta per la traduzione. */
export const T = {
  unreadAria: (n: number) => (n === 1 ? '1 messaggio non letto' : `${n} messaggi non letti`),
  dmNotifyTitle: (name: string) => `Messaggio da ${name}`,
  notifyUnsupported: "Le notifiche del browser richiedono HTTPS o l'accesso da questo PC",
}
