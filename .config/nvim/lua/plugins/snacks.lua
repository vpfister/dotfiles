return {
  "folke/snacks.nvim",
  opts = {
    picker = {
      sources = {
        explorer = {
          -- Disable git status in the file explorer.
          -- On NFS (e.g. /mnt/vast), `git status` takes 30-40s because
          -- preload-index must stat() every tracked file over the network.
          -- Git status is still available via gitsigns, statusline, and lazygit.
          git_status = false,
        },
      },
    },
  },
}
