using System;
using System.Diagnostics;
using System.IO;
using System.Windows.Forms;

internal static class ShowerProgrammerLauncher
{
    [STAThread]
    private static int Main()
    {
        string root = AppDomain.CurrentDomain.BaseDirectory;
        string script = Path.Combine(root, "Backend", "shower_programmer_gui.py");
        if (!File.Exists(script))
        {
            MessageBox.Show(
                "Could not find Backend\\shower_programmer_gui.py next to this launcher.",
                "Shower Programmer",
                MessageBoxButtons.OK,
                MessageBoxIcon.Error);
            return 1;
        }

        string bundledPython = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.UserProfile),
            ".cache",
            "codex-runtimes",
            "codex-primary-runtime",
            "dependencies",
            "python",
            "python.exe");

        string executable;
        string arguments;
        if (File.Exists(bundledPython))
        {
            executable = bundledPython;
            arguments = Quote(script);
        }
        else
        {
            executable = "py";
            arguments = "-3 " + Quote(script);
        }

        try
        {
            ProcessStartInfo startInfo = new ProcessStartInfo();
            startInfo.FileName = executable;
            startInfo.Arguments = arguments;
            startInfo.WorkingDirectory = root;
            startInfo.UseShellExecute = false;
            startInfo.CreateNoWindow = true;
            Process.Start(startInfo);
            return 0;
        }
        catch (Exception ex)
        {
            MessageBox.Show(
                "Could not start Shower Programmer.\n\n" + ex.Message,
                "Shower Programmer",
                MessageBoxButtons.OK,
                MessageBoxIcon.Error);
            return 1;
        }
    }

    private static string Quote(string value)
    {
        return "\"" + value.Replace("\"", "\\\"") + "\"";
    }
}
