using System;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Text;
using System.Windows.Forms;

[assembly: AssemblyTitle("Хряк")]
[assembly: AssemblyDescription("Портативный голосовой ассистент для Windows")]
[assembly: AssemblyProduct("Хряк (Jarvis)")]
[assembly: AssemblyCompany("hryak")]
[assembly: AssemblyVersion("1.1.2.0")]
[assembly: AssemblyFileVersion("1.1.2.0")]

namespace HryakLauncher
{
    internal static class Program
    {
        [STAThread]
        private static int Main(string[] args)
        {
            Application.EnableVisualStyles();

            string baseDir = AppDomain.CurrentDomain.BaseDirectory;
            string pythonw = Path.Combine(baseDir, "python", "pythonw.exe");
            string script = Path.Combine(baseDir, "jarvis.py");
            string config = Path.Combine(baseDir, "config.json");
            string portable = Path.Combine(baseDir, "config.portable.json");
            string example = Path.Combine(baseDir, "config.example.json");

            if (!File.Exists(config))
            {
                string template = File.Exists(portable) ? portable : example;
                if (File.Exists(template))
                {
                    try { File.Copy(template, config); }
                    catch { /* настройки создадутся значениями по умолчанию */ }
                }
            }

            if (!File.Exists(pythonw) || !File.Exists(script))
            {
                MessageBox.Show(
                    "Не найдены файлы приложения.\n\n" +
                    "Распакуйте архив целиком в отдельную папку и запустите Hryak.exe оттуда.\n\n" +
                    "Ожидались:\n" + pythonw + "\n" + script,
                    "Хряк",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Error);
                return 2;
            }

            var startInfo = new ProcessStartInfo(pythonw)
            {
                WorkingDirectory = baseDir,
                UseShellExecute = false,
                CreateNoWindow = true,
                Arguments = BuildArguments(script, args)
            };
            startInfo.EnvironmentVariables["PYTHONUTF8"] = "1";
            startInfo.EnvironmentVariables["PYTHONIOENCODING"] = "utf-8";

            try
            {
                using (Process process = Process.Start(startInfo))
                {
                    if (process == null)
                    {
                        ShowStartError(baseDir);
                        return 2;
                    }

                    process.WaitForExit();
                    if (process.ExitCode == 2)
                    {
                        MessageBox.Show(
                            "Не удалось запустить голосовой ассистент, сэр.\n\n" +
                            "Проверьте, что папка models распакована рядом с Hryak.exe.\n" +
                            "Подробности — в файле logs\\jarvis.log.",
                            "Хряк",
                            MessageBoxButtons.OK,
                            MessageBoxIcon.Warning);
                    }
                    return process.ExitCode;
                }
            }
            catch (Exception error)
            {
                MessageBox.Show(
                    "Не удалось запустить приложение.\n\n" + error.Message,
                    "Хряк",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Error);
                return 2;
            }
        }

        private static void ShowStartError(string baseDir)
        {
            MessageBox.Show(
                "Не удалось запустить pythonw.exe.\n\nПапка: " + baseDir,
                "Хряк",
                MessageBoxButtons.OK,
                MessageBoxIcon.Error);
        }

        private static string BuildArguments(string script, string[] args)
        {
            var builder = new StringBuilder();
            builder.Append(Quote(script));
            foreach (string arg in args)
            {
                builder.Append(' ');
                builder.Append(Quote(arg));
            }
            return builder.ToString();
        }

        private static string Quote(string value)
        {
            if (value.Length > 0 && value.IndexOfAny(new[] { ' ', '\t', '"' }) < 0)
            {
                return value;
            }

            var builder = new StringBuilder("\"");
            int backslashes = 0;
            foreach (char ch in value)
            {
                if (ch == '\\')
                {
                    backslashes++;
                    continue;
                }
                if (ch == '"')
                {
                    builder.Append('\\', backslashes * 2 + 1);
                    builder.Append('"');
                    backslashes = 0;
                    continue;
                }
                builder.Append('\\', backslashes);
                backslashes = 0;
                builder.Append(ch);
            }
            builder.Append('\\', backslashes * 2);
            builder.Append('"');
            return builder.ToString();
        }
    }
}
