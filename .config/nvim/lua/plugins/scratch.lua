return {
  "LintaoAmons/scratch.nvim",
  event = "VeryLazy",
  keys = {
    { "<leader>sc", "<cmd>Scratch<cr>", desc = "Scratch" },
    { "<leader>so", "<cmd>ScratchOpen<cr>", desc = "Scratch Open" },
    {
      "<leader>sm",
      function()
        require("scratch.api").createScratchFileByType("markdown")
      end,
      desc = "Scratch Markdown",
    },
  },
  opts = {
    filetypes = { "markdown", "lua", "js", "py", "sh" },
  },
}
