import { Box, Paper } from '@mui/material';

export const PageContainer = ({ children }) => {
  return (
    <Box
      display="flex"
      justifyContent="center"
      alignItems="center"
      minHeight="100vh"
      sx={{
        background: 'linear-gradient(to bottom right, #1a0033, #000000)', // dark purple to black
      }}
    >
      <Paper
        elevation={3}
        sx={{
          p: 4,
          width: '100%',
          maxWidth: 600,
          backgroundColor: 'rgba(255, 255, 255, 0.08)',
          backdropFilter: 'blur(9px)',
        }}
      >
        {children}
      </Paper>
    </Box>
  );
};
