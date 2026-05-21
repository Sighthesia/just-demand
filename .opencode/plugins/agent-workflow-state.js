export default async () => {
  return {
    "chat.message": async () => {
      // Main-session workflow state injection disabled.
      // Tasks should be inspected explicitly via list-active scripts.
      return
    },
  }
}
