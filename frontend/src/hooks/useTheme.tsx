/**
 * Tema da aplicação — por ora apenas o claro.
 *
 * O hook continua existindo (e devolvendo `isDark`) porque a camada de
 * gráficos escolhe a paleta por ele; quando o tema escuro voltar, basta
 * reintroduzir o estado aqui e os tokens escuros no main.scss.
 */
export function ThemeProvider({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}

export function useTheme() {
  return { isDark: false as const };
}
