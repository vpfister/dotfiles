return {
  {
    "iamcco/markdown-preview.nvim",
    init = function()
      -- Fixed port for remote access from laptop
      vim.g.mkdp_port = "8090"
      -- Bind to all interfaces (needed in containers)
      vim.g.mkdp_open_to_the_world = 1
      -- Don't auto-open, just print the URL
      vim.g.mkdp_auto_open = 0
      vim.g.mkdp_echo_preview_url = 1
      -- No-op browser: server-side container has no browser
      vim.g.mkdp_browser = "echo"
    end,
  },
}
